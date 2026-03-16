use actix_web::{web, App, HttpServer, HttpResponse, middleware};
use once_cell::sync::Lazy;
use regex::Regex;
use serde::{Deserialize, Serialize};
use std::env;
use std::time::Instant;
use tracing::{info, warn};

//  Structs 
#[derive(Deserialize)]
struct ExtractRequest {
    abstract_text: String,
    paper_id:      String,
    paper_title:   String,
}

#[derive(Serialize, Deserialize, Debug, Clone)]
struct Claim {
    text:        String,
    confidence:  f64,
    topic_tags:  Vec<String>,
    paper_id:    String,
    paper_title: String,
}

#[derive(Serialize)]
struct ExtractResponse {
    claims:       Vec<Claim>,
    parse_ms:     u128,
    groq_ms:      u128,
    total_ms:     u128,
    model:        String,
}

#[derive(Serialize)]
struct HealthResponse {
    status:  &'static str,
    service: &'static str,
    version: &'static str,
}

// Regex (compiled once) 
static RE_CODE_FENCE:    Lazy<Regex> = Lazy::new(|| Regex::new(r"```(?:json)?").unwrap());
static RE_TRAILING_COMMA_ARR: Lazy<Regex> = Lazy::new(|| Regex::new(r",\s*\]").unwrap());
static RE_TRAILING_COMMA_OBJ: Lazy<Regex> = Lazy::new(|| Regex::new(r",\s*\}").unwrap());
static RE_BAD_ESCAPE:    Lazy<Regex> = Lazy::new(|| Regex::new(r#"\\([^"\\/bfnrtu])"#).unwrap());

// JSON cleaner 
fn clean_json(raw: &str) -> String {
    let s = RE_CODE_FENCE.replace_all(raw, "");
    let s = s.trim();

    let start = s.find('[').unwrap_or(0);
    let end   = s.rfind(']').map(|i| i + 1).unwrap_or(s.len());
    let s = &s[start..end];

    let s = RE_TRAILING_COMMA_ARR.replace_all(s, "]");
    let s = RE_TRAILING_COMMA_OBJ.replace_all(&s, "}");
    let s = RE_BAD_ESCAPE.replace_all(&s, r"\\$1");

    s.to_string()
}

// Claim validator 
fn validate_claims(
    raw: &serde_json::Value,
    paper_id: &str,
    paper_title: &str,
) -> Vec<Claim> {
    raw.as_array()
        .unwrap_or(&vec![])
        .iter()
        .filter_map(|c| {
            let text = c["text"].as_str()?.to_string();
            if text.is_empty() { return None; }

            let confidence = c["confidence"].as_f64().unwrap_or(0.8);
            if confidence < 0.6 { return None; }

            let topic_tags = c["topic_tags"]
                .as_array()
                .map(|arr| arr.iter().filter_map(|t| t.as_str().map(String::from)).collect())
                .unwrap_or_default();

            Some(Claim {
                text,
                confidence,
                topic_tags,
                paper_id:    paper_id.to_string(),
                paper_title: paper_title.to_string(),
            })
        })
        .collect()
}

// Groq HTTP call 
fn build_prompt(abstract_text: &str) -> String {
    format!(
        "Extract 3-5 factual claims from this abstract.\n\
         Return ONLY a JSON array like this exact format:\n\
         [{{\"text\": \"claim here\", \"confidence\": 0.9, \"topic_tags\": [\"tag\"]}}]\n\n\
         Abstract:\n{}\n\nJSON:",
        abstract_text
    )
}

async fn call_groq(
    client: &reqwest::Client,
    api_key: &str,
    abstract_text: &str,
) -> Result<String, String> {
    let body = serde_json::json!({
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "user", "content": build_prompt(abstract_text)}],
        "temperature": 0.1,
        "max_tokens": 1024
    });

    let res = client
        .post("https://api.groq.com/openai/v1/chat/completions")
        .header("Authorization", format!("Bearer {}", api_key))
        .header("Content-Type", "application/json")
        .json(&body)
        .send()
        .await
        .map_err(|e| format!("reqwest error: {e}"))?;

    if !res.status().is_success() {
        return Err(format!("Groq HTTP {}", res.status()));
    }

    let json: serde_json::Value = res.json().await
        .map_err(|e| format!("parse error: {e}"))?;

    json["choices"][0]["message"]["content"]
        .as_str()
        .map(String::from)
        .ok_or_else(|| "empty content".to_string())
}

// Handlers 
async fn health() -> HttpResponse {
    HttpResponse::Ok().json(HealthResponse {
        status:  "ok",
        service: "claim-parser",
        version: "0.1.0",
    })
}

async fn extract(
    req: web::Json<ExtractRequest>,
    data: web::Data<AppState>,
) -> HttpResponse {
    let total_start = Instant::now();

    let api_key = match &data.groq_api_key {
        Some(k) => k.clone(),
        None => {
            warn!("GROQ_API_KEY tidak ada");
            return HttpResponse::ServiceUnavailable()
                .json(serde_json::json!({"error": "GROQ_API_KEY not set"}));
        }
    };

    // Groq API call 
    let groq_start = Instant::now();
    let raw_content = match call_groq(&data.http_client, &api_key, &req.abstract_text).await {
        Ok(c) => c,
        Err(e) => {
            warn!("Groq error: {e}");
            return HttpResponse::InternalServerError()
                .json(serde_json::json!({"error": e}));
        }
    };
    let groq_ms = groq_start.elapsed().as_millis();

    // Parse + validate 
    let parse_start = Instant::now();
    let cleaned = clean_json(&raw_content);
    let claims = match serde_json::from_str::<serde_json::Value>(&cleaned) {
        Ok(v) => validate_claims(&v, &req.paper_id, &req.paper_title),
        Err(e) => {
            warn!("JSON parse error: {e} | raw: {cleaned}");
            vec![]
        }
    };
    let parse_ms  = parse_start.elapsed().as_millis();
    let total_ms  = total_start.elapsed().as_millis();

    info!(
        paper_id = %req.paper_id,
        claims   = claims.len(),
        groq_ms  = groq_ms,
        parse_ms = parse_ms,
        total_ms = total_ms,
        "extracted"
    );

    HttpResponse::Ok().json(ExtractResponse {
        claims,
        parse_ms,
        groq_ms,
        total_ms,
        model: "llama-3.3-70b-versatile".to_string(),
    })
}

// App state 
struct AppState {
    groq_api_key: Option<String>,
    http_client:  reqwest::Client,
}

// Main 
#[tokio::main]
async fn main() -> std::io::Result<()> {
    tracing_subscriber::fmt::init();

    let port = env::var("CLAIM_PARSER_PORT")
        .unwrap_or_else(|_| "8002".to_string())
        .parse::<u16>()
        .unwrap_or(8002);

    let groq_api_key = env::var("GROQ_API_KEY").ok();
    if groq_api_key.is_none() {
        warn!("GROQ_API_KEY tidak di-set — service akan return error");
    }

    let state = web::Data::new(AppState {
        groq_api_key,
        http_client: reqwest::Client::builder()
            .timeout(std::time::Duration::from_secs(60))
            .build()
            .unwrap(),
    });

    info!("claim-parser listening on :{port}");

    HttpServer::new(move || {
        App::new()
            .app_data(state.clone())
            .app_data(web::JsonConfig::default().limit(1_048_576))
            .route("/health", web::get().to(health))
            .route("/extract", web::post().to(extract))
    })
    .bind(("0.0.0.0", port))?
    .run()
    .await
}
