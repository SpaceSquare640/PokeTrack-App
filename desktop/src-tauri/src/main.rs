// PokéTrack native desktop shell (Tauri).
//
// The desktop app is a thin, native Rust shell that reuses the existing web UI:
// on launch it spawns the Flask server as a child process, waits for its port
// to come up, then opens a native window pointed at it. The window IS the fusion
// web UI — full CSS fidelity — with native chrome, and the server is killed on
// exit. In a packaged build the `python run_web.py` command is replaced by a
// bundled sidecar; for the POC it runs the repo's server directly.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::net::TcpStream;
use std::path::PathBuf;
use std::process::{Child, Command};
use std::sync::Mutex;
use std::thread;
use std::time::Duration;

use tauri::{Manager, WebviewUrl, WebviewWindowBuilder};

const HOST: &str = "127.0.0.1";
const PORT: u16 = 5000;
const URL: &str = "http://127.0.0.1:5000/";

/// Holds the spawned server process so it can be killed on exit.
struct ServerProcess(Mutex<Option<Child>>);

/// Repo root, relative to this crate (desktop/src-tauri) — dev fallback only.
fn repo_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..").join("..")
}

fn port_open() -> bool {
    TcpStream::connect((HOST, PORT)).is_ok()
}

/// Locate the bundled server sidecar in the app's resource dir, if present.
fn bundled_server(app: &tauri::App) -> Option<PathBuf> {
    let res = app.path().resource_dir().ok()?;
    for cand in [
        res.join("binaries").join("poketrack-server.exe"),
        res.join("poketrack-server.exe"),
    ] {
        if cand.exists() {
            return Some(cand);
        }
    }
    None
}

/// Start the server: the bundled sidecar when installed, else `python run_web.py`
/// from the repo (dev). Both honour the POKETRACK_WEB_* env vars.
fn spawn_server(app: &tauri::App) -> std::io::Result<Child> {
    let mut cmd = match bundled_server(app) {
        Some(exe) => Command::new(exe),
        None => {
            let mut c = Command::new("python");
            c.arg("run_web.py").current_dir(repo_root());
            c
        }
    };
    let child = cmd
        .env("POKETRACK_WEB_HOST", HOST)
        .env("POKETRACK_WEB_PORT", PORT.to_string())
        .spawn()?;
    // Tie the server's lifetime to this app so it can never orphan (the PyInstaller
    // onefile server spawns its own child, which a plain kill() would miss).
    #[cfg(windows)]
    bind_to_job(&child);
    Ok(child)
}

/// Assign the child (and any grandchildren) to a Job Object that kills them when
/// this process exits by ANY means — clean quit, crash, or Task Manager kill.
/// The job handle is intentionally leaked so it lives for the app's lifetime.
#[cfg(windows)]
fn bind_to_job(child: &Child) {
    use std::os::windows::io::AsRawHandle;
    use windows_sys::Win32::System::JobObjects::{
        AssignProcessToJobObject, CreateJobObjectW, JobObjectExtendedLimitInformation,
        SetInformationJobObject, JOBOBJECT_EXTENDED_LIMIT_INFORMATION,
        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
    };
    unsafe {
        let job = CreateJobObjectW(std::ptr::null(), std::ptr::null());
        if job.is_null() {
            return;
        }
        let mut info: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = std::mem::zeroed();
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        SetInformationJobObject(
            job,
            JobObjectExtendedLimitInformation,
            &info as *const _ as *const core::ffi::c_void,
            std::mem::size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
        );
        AssignProcessToJobObject(job, child.as_raw_handle() as _);
    }
}

fn main() {
    tauri::Builder::default()
        .manage(ServerProcess(Mutex::new(None)))
        .setup(|app| {
            let handle = app.handle().clone();

            // Reuse an already-running server (e.g. during dev); else spawn one.
            if !port_open() {
                match spawn_server(app) {
                    Ok(child) => {
                        *app.state::<ServerProcess>().0.lock().unwrap() = Some(child);
                    }
                    Err(e) => eprintln!("[poketrack] failed to spawn server: {e}"),
                }
            }

            // Off the main thread: wait for the server, then open the window.
            thread::spawn(move || {
                for _ in 0..150 {
                    if port_open() {
                        break;
                    }
                    thread::sleep(Duration::from_millis(200));
                }
                let h = handle.clone();
                let _ = handle.run_on_main_thread(move || {
                    match WebviewWindowBuilder::new(
                        &h,
                        "main",
                        WebviewUrl::External(URL.parse().unwrap()),
                    )
                    .title("PokéTrack")
                    .inner_size(1180.0, 780.0)
                    .min_inner_size(940.0, 600.0)
                    .build()
                    {
                        Ok(_) => {}
                        Err(e) => eprintln!("[poketrack] failed to open window: {e}"),
                    }
                });
            });

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app_handle, event| {
            if let tauri::RunEvent::Exit = event {
                if let Some(mut child) = app_handle.state::<ServerProcess>().0.lock().unwrap().take()
                {
                    let _ = child.kill();
                }
            }
        });
}
