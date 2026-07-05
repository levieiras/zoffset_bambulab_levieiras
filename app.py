import json
import os
import shutil
import threading
import time
import uuid
import zipfile
from pathlib import Path

from flask import (
    Flask,
    after_this_request,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)

import database
import zoffset_tool
from zoffset_tool import process_file

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "zoffset-dev-key-change-in-production")

APP_ROOT = os.environ.get("APP_ROOT", "")


@app.context_processor
def inject_app_root():
    return {"APP_ROOT": APP_ROOT}

BASE_DIR = Path(__file__).parent
UPLOADS_DIR = BASE_DIR / "uploads"
OUTPUTS_DIR = BASE_DIR / "outputs"

UPLOADS_DIR.mkdir(exist_ok=True)
OUTPUTS_DIR.mkdir(exist_ok=True)

MAX_CONTENT_LENGTH = 500 * 1024 * 1024  # 500MB
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH

jobs = {}


def cleanup_old_outputs():
    """Remove pastas de output com mais de 5 minutos."""
    while True:
        time.sleep(300)
        now = time.time()
        if OUTPUTS_DIR.exists():
            for job_dir in OUTPUTS_DIR.iterdir():
                if job_dir.is_dir():
                    age = now - job_dir.stat().st_mtime
                    if age > 300:
                        shutil.rmtree(job_dir, ignore_errors=True)
        if UPLOADS_DIR.exists():
            for f in UPLOADS_DIR.iterdir():
                if f.is_file():
                    age = now - f.stat().st_mtime
                    if age > 300:
                        f.unlink(missing_ok=True)


def run_job(job_id, valid_files, rejected, selected_printers):
    """Executa o processamento em background thread."""
    job = jobs[job_id]
    job_dir = OUTPUTS_DIR / job_id
    job_dir.mkdir(exist_ok=True)

    multiple_printers = len(selected_printers) > 1
    job["multiple_printers"] = multiple_printers
    job["rejected"] = rejected

    total_steps = 0
    for f in valid_files:
        if multiple_printers:
            total_steps += len(selected_printers)
        else:
            total_steps += 1
    job["total"] = total_steps

    processed_names = []

    for file in valid_files:
        upload_path = UPLOADS_DIR / file.filename
        upload_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            if multiple_printers:
                for key, printer_info in selected_printers.items():
                    printer_name = zoffset_tool.sanitize_name(printer_info["name"])
                    printer_dir = job_dir / printer_name
                    printer_dir.mkdir(exist_ok=True)
                    single = {key: printer_info}
                    res = process_file(upload_path, single, printer_dir)
                    for name, success, detail in res:
                        rel_path = f"{printer_name}/{name}"
                        job["results"].append((file.filename, rel_path, success, detail))
                        if success:
                            job["successful"].append((file.filename, rel_path, success, detail))
                        else:
                            job["failed"].append((file.filename, rel_path, success, detail))
                    job["current"] += 1
            else:
                results = process_file(upload_path, selected_printers, job_dir)
                for name, success, detail in results:
                    job["results"].append((file.filename, name, success, detail))
                    if success:
                        job["successful"].append((file.filename, name, success, detail))
                    else:
                        job["failed"].append((file.filename, name, success, detail))
                job["current"] += 1
        except Exception as e:
            job["results"].append((file.filename, file.filename, False, f"Erro: {e}"))
            job["failed"].append((file.filename, file.filename, False, f"Erro: {e}"))
            job["current"] += 1
        finally:
            upload_path.unlink(missing_ok=True)
            processed_names.append(file.filename)

    job["processed_names"] = processed_names
    job["done"] = True


@app.template_filter("timestamp")
def timestamp_filter(dt):
    if dt is None:
        return ""
    if isinstance(dt, str):
        return dt
    return dt.strftime("%d/%m/%Y %H:%M")


@app.route("/")
def index():
    printers = database.get_printers()
    return render_template("index.html", printers=printers)


@app.route("/upload", methods=["POST"])
def upload():
    printers = database.get_printers()
    if not printers:
        return jsonify({"error": "Nenhuma impressora configurada. Adicione impressoras primeiro."}), 400

    files = request.files.getlist("files")
    if not files or all(f.filename == "" for f in files):
        return jsonify({"error": "Nenhum arquivo selecionado."}), 400

    valid_files = [f for f in files if f.filename.lower().endswith(".3mf")]
    if not valid_files:
        return jsonify({"error": "Apenas arquivos .3mf sao aceitos."}), 400

    rejected = [f.filename for f in files if not f.filename.lower().endswith(".3mf")]

    selected_ids = request.form.getlist("printers")
    if not selected_ids:
        return jsonify({"error": "Selecione pelo menos uma impressora."}), 400

    selected_printers = {}
    for i, p in enumerate(printers):
        if str(p["id"]) in selected_ids:
            selected_printers[f"imp{i+1}"] = {
                "name": p["name"],
                "z_offset": p["z_offset"],
            }

    job_id = uuid.uuid4().hex[:12]

    for file in valid_files:
        upload_path = UPLOADS_DIR / file.filename
        upload_path.parent.mkdir(parents=True, exist_ok=True)
        file.save(str(upload_path))

    jobs[job_id] = {
        "current": 0,
        "total": 0,
        "done": False,
        "results": [],
        "successful": [],
        "failed": [],
        "rejected": rejected,
        "processed_names": [],
        "multiple_printers": False,
        "created_at": time.time(),
    }

    thread = threading.Thread(target=run_job, args=(job_id, valid_files, rejected, selected_printers), daemon=True)
    thread.start()

    return jsonify({"job_id": job_id})


@app.route("/progress/<job_id>")
def progress(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job nao encontrado"}), 404

    return jsonify({
        "current": job["current"],
        "total": job["total"],
        "done": job["done"],
    })


@app.route("/results/<job_id>")
def results(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job nao encontrado"}), 404

    return jsonify({
        "results": job["results"],
        "successful": job["successful"],
        "failed": job["failed"],
        "rejected": job["rejected"],
        "job_id": job_id,
        "processed_names": job["processed_names"],
        "multiple_printers": job["multiple_printers"],
    })


@app.route("/download/<job_id>/<path:filename>")
def download(job_id, filename):
    if not filename:
        flash("Arquivo invalido.", "error")
        return redirect(url_for("index"))

    job_dir = OUTPUTS_DIR / job_id
    if not job_dir.exists():
        flash("Arquivo nao encontrado ou expirado.", "error")
        return redirect(url_for("index"))

    file_path = job_dir / filename
    if not file_path.exists():
        flash("Arquivo nao encontrado.", "error")
        return redirect(url_for("index"))

    @after_this_request
    def cleanup(response):
        try:
            file_path.unlink(missing_ok=True)
            parent = file_path.parent
            if parent != job_dir and not any(parent.iterdir()):
                parent.rmdir()
            if not any(job_dir.iterdir()):
                shutil.rmtree(job_dir, ignore_errors=True)
        except Exception:
            pass
        return response

    return send_from_directory(str(file_path.parent), file_path.name, as_attachment=True)


@app.route("/download-all/<job_id>")
def download_all(job_id):
    job_dir = OUTPUTS_DIR / job_id
    if not job_dir.exists():
        flash("Arquivo nao encontrado ou expirado.", "error")
        return redirect(url_for("index"))

    files = list(job_dir.rglob("*.3mf"))
    if not files:
        flash("Nenhum arquivo processado encontrado.", "error")
        return redirect(url_for("index"))

    zip_path = job_dir / f"processed_{job_id}.zip"
    with zipfile.ZipFile(str(zip_path), "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            arcname = f.relative_to(job_dir)
            zf.write(str(f), str(arcname))

    @after_this_request
    def cleanup(response):
        try:
            shutil.rmtree(job_dir, ignore_errors=True)
        except Exception:
            pass
        return response

    return send_from_directory(str(job_dir), zip_path.name, as_attachment=True)


@app.route("/cleanup/<job_id>", methods=["POST"])
def cleanup_job(job_id):
    job_dir = OUTPUTS_DIR / job_id
    if job_dir.exists():
        shutil.rmtree(job_dir, ignore_errors=True)
    jobs.pop(job_id, None)
    return jsonify({"ok": True})


@app.route("/printers")
def printers_page():
    printers = database.get_printers()
    return render_template("printers.html", printers=printers)


@app.route("/printers/add", methods=["POST"])
def add_printer():
    name = request.form.get("name", "").strip()
    z_offset_str = request.form.get("z_offset", "").strip()

    if not name:
        flash("Nome da impressora e obrigatorio.", "error")
        return redirect(url_for("printers_page"))

    try:
        z_offset = float(z_offset_str)
    except (ValueError, TypeError):
        flash("Z-offset invalido. Use um numero como -0.06 ou 0.00.", "error")
        return redirect(url_for("printers_page"))

    database.add_printer(name, z_offset)
    flash(f'Impressora "{name}" adicionada com sucesso.', "success")
    return redirect(url_for("printers_page"))


@app.route("/printers/edit/<int:printer_id>", methods=["POST"])
def edit_printer(printer_id):
    name = request.form.get("name", "").strip()
    z_offset_str = request.form.get("z_offset", "").strip()

    if not name:
        flash("Nome da impressora e obrigatorio.", "error")
        return redirect(url_for("printers_page"))

    try:
        z_offset = float(z_offset_str)
    except (ValueError, TypeError):
        flash("Z-offset invalido. Use um numero como -0.06 ou 0.00.", "error")
        return redirect(url_for("printers_page"))

    database.update_printer(printer_id, name, z_offset)
    flash(f'Impressora "{name}" atualizada com sucesso.', "success")
    return redirect(url_for("printers_page"))


@app.route("/printers/delete/<int:printer_id>", methods=["POST"])
def delete_printer(printer_id):
    database.delete_printer(printer_id)
    flash("Impressora removida.", "success")
    return redirect(url_for("printers_page"))


if __name__ == "__main__":
    database.init_db()
    database.seed_from_json_if_empty()

    cleanup_thread = threading.Thread(target=cleanup_old_outputs, daemon=True)
    cleanup_thread.start()

    app.run(debug=True, host="0.0.0.0", port=5000)
