use actix_web::{web, App, HttpServer, HttpResponse};
use once_cell::sync::Lazy;
use regex::Regex;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::env;
use std::time::Instant;
use tokio_postgres::NoTls;
use tracing::{info, warn};
use unicode_segmentation::UnicodeSegmentation;

#[derive(Deserialize)]
struct SimilarityRequest {
    query: String,
    top_k: Option<usize>,
    method: Option<String>,
    threshold: Option<f64>,
}

#[derive(Deserialize)]
struct BatchRequest {
    claims: Vec<ClaimInput>,
    top_k: Option<usize>,
    method: Option<String>,
    threshold: Option<f64>,
}

#[derive(Deserialize)]
struct ClaimInput {
    text: String,
    paper_id: Option<String>,
}

#[derive(Serialize, Clone)]
struct SimilarChunk {
    chunk_id: String,
    text: String,
    tfidf_score: f64,
    vector_score: f64,
    hybrid_score: f64,
}

#[derive(Serialize)]
struct SimilarityResponse {
    query: String,
    chunks: Vec<SimilarChunk>,
    top_score: f64,
    has_similar: bool,
    method: String,
    total_ms: u128,
}

#[derive(Serialize)]
struct BatchResult {
    text: String,
    paper_id: Option<String>,
    similar_chunks: Vec<SimilarChunk>,
    similarity_score: f64,
    has_similar: bool,
}

#[derive(Serialize)]
struct BatchResponse {
    results: Vec<BatchResult>,
    total_claims: usize,
    total_ms: u128,
    method: String,
}

#[derive(Serialize)]
struct HealthResponse {
    status: &'static str,
    service: &'static str,
    version: &'static str,
    db: String,
}

static RE_PUNCT: Lazy<Regex> = Lazy::new(|| Regex::new(r"[^\w\s]").unwrap());

static STOPWORDS: Lazy<std::collections::HashSet<&'static str>> = Lazy::new(|| {
    ["the","a","an","and","or","but","in","on","at","to","for","of","with","by",
     "from","is","are","was","were","be","been","being","have","has","had","do",
     "does","did","will","would","could","should","may","might","shall","can",
     "that","this","these","those","it","its","as","than","then","not","no",
     "nor","so","yet","both","either","neither","each","more","most","other",
     "some","such","into","through","during","before","after","above","below",
     "between","out","off","over","under","again","further","while","also",
     "there","their","they","which","who","whom","we","our","you","your","he",
     "she","him","her","his","my","me","i"]
    .iter().cloned().collect()
});

fn tokenize(text: &str) -> Vec<String> {
    let lower = text.to_lowercase();
    let cleaned = RE_PUNCT.replace_all(&lower, " ");
    cleaned.unicode_words()
        .filter(|w| w.len() > 2 && !STOPWORDS.contains(*w))
        .map(String::from)
        .collect()
}

fn term_freq(tokens: &[String]) -> HashMap<String, f64> {
    let mut tf: HashMap<String, f64> = HashMap::new();
    for t in tokens { *tf.entry(t.clone()).or_insert(0.0) += 1.0; }
    let len = tokens.len() as f64;
    if len > 0.0 { for v in tf.values_mut() { *v /= len; } }
    tf
}

fn cosine_similarity(a: &HashMap<String, f64>, b: &HashMap<String, f64>) -> f64 {
    let dot: f64 = a.iter().filter_map(|(k, v)| b.get(k).map(|bv| v * bv)).sum();
    let mag_a: f64 = a.values().map(|v| v * v).sum::<f64>().sqrt();
    let mag_b: f64 = b.values().map(|v| v * v).sum::<f64>().sqrt();
    if mag_a == 0.0 || mag_b == 0.0 { return 0.0; }
    dot / (mag_a * mag_b)
}

fn bm25_score(query: &str, doc: &str) -> f64 {
    let k1 = 1.5_f64; let b = 0.75_f64; let avg_doc_len = 25.0_f64;
    let q_tokens = tokenize(query);
    let d_tokens = tokenize(doc);
    let doc_len = d_tokens.len() as f64;
    let mut doc_tf: HashMap<&str, usize> = HashMap::new();
    for t in &d_tokens { *doc_tf.entry(t.as_str()).or_insert(0) += 1; }
    let mut score = 0.0_f64;
    for term in &q_tokens {
        if let Some(&tf) = doc_tf.get(term.as_str()) {
            let tf_f = tf as f64;
            score += (tf_f * (k1 + 1.0)) / (tf_f + k1 * (1.0 - b + b * doc_len / avg_doc_len));
        }
    }
    (score / (q_tokens.len() as f64 + 1.0)).min(1.0)
}

fn lexical_score(query: &str, doc: &str) -> f64 {
    let q_tf = term_freq(&tokenize(query));
    let d_tf = term_freq(&tokenize(doc));
    (cosine_similarity(&q_tf, &d_tf) + bm25_score(query, doc)) / 2.0
}

struct AppState { db_url: String }

async fn get_db(state: &AppState) -> Result<tokio_postgres::Client, String> {
    let (client, conn) = tokio_postgres::connect(&state.db_url, NoTls)
        .await.map_err(|e| format!("DB error: {e}"))?;
    tokio::spawn(async move { if let Err(e) = conn.await { warn!("DB conn error: {e}"); } });
    Ok(client)
}

async fn fetch_kb(client: &tokio_postgres::Client) -> Vec<(String, String)> {
    client.query(
        "SELECT log_id::text, action FROM audit_log WHERE action IS NOT NULL AND LENGTH(action) > 20 AND action LIKE 'claim:%' LIMIT 5000",
        &[]
    ).await.unwrap_or_default()
     .iter().map(|r| (r.get::<_,String>(0), r.get::<_,String>(1))).collect()
}

fn score_chunks(query: &str, kb: &[(String, String)], top_k: usize, threshold: f64) -> Vec<SimilarChunk> {
    let q_tokens: std::collections::HashSet<String> = tokenize(query).into_iter().collect();
    let mut scored: Vec<SimilarChunk> = kb.iter().map(|(id, text)| {
        let tfidf = lexical_score(query, text);
        let d_tokens: std::collections::HashSet<String> = tokenize(text).into_iter().collect();
        let overlap = q_tokens.intersection(&d_tokens).count() as f64;
        let union = q_tokens.union(&d_tokens).count() as f64;
        let jaccard = if union > 0.0 { overlap / union } else { 0.0 };
        let vector_score = (jaccard * 0.6 + tfidf * 0.4).min(1.0);
        let hybrid_score = (tfidf * 0.4 + vector_score * 0.6).min(1.0);
        SimilarChunk { chunk_id: id.clone(), text: text.clone(), tfidf_score: tfidf, vector_score, hybrid_score }
    }).collect();
    scored.sort_by(|a, b| b.hybrid_score.partial_cmp(&a.hybrid_score).unwrap());
    scored.into_iter().filter(|c| c.hybrid_score >= threshold).take(top_k).collect()
}

async fn health(data: web::Data<AppState>) -> HttpResponse {
    let db = match get_db(&data).await {
        Ok(c) => match c.query_one("SELECT 1", &[]).await {
            Ok(_) => "connected".to_string(),
            Err(e) => format!("error: {e}"),
        },
        Err(e) => e,
    };
    HttpResponse::Ok().json(HealthResponse { status: "ok", service: "similarity-engine", version: "0.1.0", db })
}

async fn similarity(req: web::Json<SimilarityRequest>, data: web::Data<AppState>) -> HttpResponse {
    let start = Instant::now();
    let top_k = req.top_k.unwrap_or(3).min(20);
    let method = req.method.clone().unwrap_or_else(|| "hybrid".to_string());
    let threshold = req.threshold.unwrap_or(0.05);
    let db = match get_db(&data).await {
        Ok(c) => c,
        Err(e) => return HttpResponse::ServiceUnavailable().json(serde_json::json!({"error": e})),
    };
    let kb = fetch_kb(&db).await;
    let chunks = score_chunks(&req.query, &kb, top_k, threshold);
    let top_score = chunks.first().map(|c| c.hybrid_score).unwrap_or(0.0);
    let total_ms = start.elapsed().as_millis();
    info!(chunks = chunks.len(), top_score = top_score, total_ms = total_ms, "similarity");
    HttpResponse::Ok().json(SimilarityResponse {
        query: req.query.clone(), chunks, top_score,
        has_similar: top_score >= threshold, method, total_ms,
    })
}

async fn batch_similarity(req: web::Json<BatchRequest>, data: web::Data<AppState>) -> HttpResponse {
    let start = Instant::now();
    let top_k = req.top_k.unwrap_or(3).min(20);
    let method = req.method.clone().unwrap_or_else(|| "hybrid".to_string());
    let threshold = req.threshold.unwrap_or(0.05);
    let db = match get_db(&data).await {
        Ok(c) => c,
        Err(e) => return HttpResponse::ServiceUnavailable().json(serde_json::json!({"error": e})),
    };
    let kb = fetch_kb(&db).await;
    let results: Vec<BatchResult> = req.claims.iter().map(|claim| {
        let chunks = score_chunks(&claim.text, &kb, top_k, threshold);
        let similarity_score = chunks.first().map(|c| c.hybrid_score).unwrap_or(0.0);
        BatchResult {
            text: claim.text.clone(), paper_id: claim.paper_id.clone(),
            similar_chunks: chunks, similarity_score,
            has_similar: similarity_score >= threshold,
        }
    }).collect();
    let total_ms = start.elapsed().as_millis();
    info!(claims = results.len(), total_ms = total_ms, "batch similarity");
    HttpResponse::Ok().json(BatchResponse { results, total_claims: req.claims.len(), total_ms, method })
}

#[tokio::main]
async fn main() -> std::io::Result<()> {
    tracing_subscriber::fmt::init();
    let port = env::var("SIMILARITY_ENGINE_PORT").unwrap_or_else(|_| "8003".to_string())
        .parse::<u16>().unwrap_or(8003);
    let db_url = {
        let host = env::var("POSTGRES_HOST").unwrap_or_else(|_| "localhost".to_string());
        let port_db = env::var("POSTGRES_PORT").unwrap_or_else(|_| "5432".to_string());
        let db = env::var("POSTGRES_DB").unwrap_or_else(|_| "clinical_agent".to_string());
        let user = env::var("POSTGRES_USER").unwrap_or_else(|_| "maliki".to_string());
        let pass = env::var("POSTGRES_PASSWORD").unwrap_or_default();
        format!("postgresql://{user}:{pass}@{host}:{port_db}/{db}")
    };
    let state = web::Data::new(AppState { db_url });
    info!("similarity-engine listening on :{port}");
    HttpServer::new(move || {
        App::new()
            .app_data(state.clone())
            .app_data(web::JsonConfig::default().limit(1_048_576))
            .route("/health", web::get().to(health))
            .route("/similarity", web::post().to(similarity))
            .route("/batch", web::post().to(batch_similarity))
    })
    .bind(("0.0.0.0", port))?.run().await
}
