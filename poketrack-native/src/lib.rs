//! PokéTrack native fast path (Rust + PyO3).
//!
//! Two pure functions mirror the hot loops in the Python data layer:
//!
//! * [`parse_feed`]      — parse the whole ScrapedDuck JSON feed into a list of
//!   plain dicts (fields + distilled highlights + inferred region) in one call,
//!   replacing the per-item Python loop in `Event.from_scrapedduck`.
//! * [`classify_region`] — infer a region from name/heading using an ordered
//!   keyword list, mirroring `poketrack.core.regions.classify`.
//!
//! The Python side (`poketrack/core/native.py`) imports this module when it is
//! installed and falls back to pure Python when it is not, so the app runs
//! identically with or without the compiled extension.
//!
//! Datetimes are returned as the *raw* source strings (or `None`); the Python
//! layer normalises them to naive-local via its existing `_parse_dt`, preserving
//! the timezone-collapsing behaviour the rest of the app depends on.

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use serde_json::Value;

/// First keyword found (case-insensitive substring) wins; else `"Global"`.
/// Order of `keywords` is significant and matches the Python semantics exactly.
fn classify(name: &str, heading: &str, keywords: &[(String, String)]) -> String {
    let haystack = format!("{name} {heading}").to_lowercase();
    for (keyword, region) in keywords {
        if !keyword.is_empty() && haystack.contains(keyword.as_str()) {
            return region.clone();
        }
    }
    "Global".to_string()
}

/// Read a string field from a JSON object, defaulting to `""`.
fn str_field<'a>(item: &'a Value, key: &str) -> &'a str {
    item.get(key).and_then(Value::as_str).unwrap_or("")
}

/// Infer a region from `name`/`heading` using an ordered `(keyword, region)` list.
#[pyfunction]
fn classify_region(name: &str, heading: &str, keywords: Vec<(String, String)>) -> String {
    classify(name, heading, &keywords)
}

/// Parse the ScrapedDuck events feed (raw JSON text) into a list of dicts.
///
/// Each dict carries: `event_id, name, event_type, heading, link, image,
/// start, end, region, bosses, promocodes, has_spawns, has_research`.
/// Raises `ValueError` if the text isn't a JSON array (mirrors `ParseError`).
#[pyfunction]
fn parse_feed<'py>(
    py: Python<'py>,
    json_str: &str,
    keywords: Vec<(String, String)>,
) -> PyResult<Bound<'py, PyList>> {
    let data: Value = serde_json::from_str(json_str)
        .map_err(|e| pyo3::exceptions::PyValueError::new_err(format!("invalid JSON: {e}")))?;
    let arr = data.as_array().ok_or_else(|| {
        pyo3::exceptions::PyValueError::new_err("expected a JSON array of events")
    })?;

    let out = PyList::empty(py);
    for item in arr {
        if !item.is_object() {
            continue;
        }

        // name: name -> heading -> "Untitled event"
        let name = {
            let n = str_field(item, "name");
            if !n.is_empty() {
                n
            } else {
                let h = str_field(item, "heading");
                if h.is_empty() {
                    "Untitled event"
                } else {
                    h
                }
            }
        };
        let heading = str_field(item, "heading");
        let event_type = str_field(item, "eventType");
        let link = str_field(item, "link");
        let image = str_field(item, "image");

        // event_id: eventID -> link -> name
        let event_id = {
            let e = str_field(item, "eventID");
            if !e.is_empty() {
                e.to_string()
            } else if !link.is_empty() {
                link.to_string()
            } else {
                name.to_string()
            }
        };

        // start/end kept as raw strings; Python normalises tz-aware -> naive local.
        let start = item.get("start").and_then(Value::as_str);
        let end = item.get("end").and_then(Value::as_str);

        // Distil highlights out of extraData (raid bosses, promo codes, flags).
        let mut bosses: Vec<String> = Vec::new();
        let mut promocodes: Vec<String> = Vec::new();
        let mut has_spawns = false;
        let mut has_research = false;
        if let Some(extra) = item.get("extraData").filter(|v| v.is_object()) {
            if let Some(raid) = extra.get("raidbattles").filter(|v| v.is_object()) {
                if let Some(list) = raid.get("bosses").and_then(Value::as_array) {
                    for boss in list {
                        if let Some(bn) = boss.get("name").and_then(Value::as_str) {
                            if !bn.is_empty() {
                                bosses.push(bn.to_string());
                            }
                        }
                    }
                }
            }
            if let Some(list) = extra.get("promocodes").and_then(Value::as_array) {
                for p in list {
                    if let Some(code) = p.as_str() {
                        promocodes.push(code.to_string());
                    }
                }
            }
            if let Some(generic) = extra.get("generic").filter(|v| v.is_object()) {
                has_spawns = generic
                    .get("hasSpawns")
                    .and_then(Value::as_bool)
                    .unwrap_or(false);
                has_research = generic
                    .get("hasFieldResearchTasks")
                    .and_then(Value::as_bool)
                    .unwrap_or(false);
            }
        }

        let region = classify(name, heading, &keywords);

        let dict = PyDict::new(py);
        dict.set_item("event_id", event_id)?;
        dict.set_item("name", name)?;
        dict.set_item("event_type", event_type)?;
        dict.set_item("heading", heading)?;
        dict.set_item("link", link)?;
        dict.set_item("image", image)?;
        dict.set_item("start", start)?; // Option<&str> -> str | None
        dict.set_item("end", end)?;
        dict.set_item("region", region)?;
        dict.set_item("bosses", bosses)?;
        dict.set_item("promocodes", promocodes)?;
        dict.set_item("has_spawns", has_spawns)?;
        dict.set_item("has_research", has_research)?;
        out.append(dict)?;
    }
    Ok(out)
}

/// The `poketrack_native` Python module.
#[pymodule]
fn poketrack_native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(parse_feed, m)?)?;
    m.add_function(wrap_pyfunction!(classify_region, m)?)?;
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    Ok(())
}
