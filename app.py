from flask import Flask, render_template, request, redirect, url_for, send_file
import json
import os
import tempfile

app = Flask(__name__)

DATA_FILE = "data.json"


def load_data():
    if not os.path.exists(DATA_FILE):
        return {"livros": [], "desejos": []}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def ordenar_livros(livros):
    # ☐ primeiro, ☑ depois, alfabético pelo título
    def chave(item):
        estado = 1 if item.get("concluido", False) else 0
        return (estado, item.get("titulo", "").strip().lower())
    livros.sort(key=chave)


def next_id(data):
    ids = [x.get("id", 0) for x in data.get("livros", [])] + [x.get("id", 0) for x in data.get("desejos", [])]
    return (max(ids) + 1) if ids else 1


def normalize_loaded_data(raw):
    """Aceita ficheiros exportados por esta app e também tentativas 'quase certas'."""
    if not isinstance(raw, dict):
        return {"livros": [], "desejos": []}

    livros_in = raw.get("livros", [])
    desejos_in = raw.get("desejos", [])

    livros = []
    desejos = []

    # Livros esperados: {id:int, titulo:str, concluido:bool}
    if isinstance(livros_in, list):
        for item in livros_in:
            if isinstance(item, dict):
                titulo = str(item.get("titulo", "")).strip()
                if not titulo:
                    continue
                livros.append({
                    "id": int(item.get("id", 0)) if str(item.get("id", "")).isdigit() else 0,
                    "titulo": titulo,
                    "concluido": bool(item.get("concluido", False))
                })
            elif isinstance(item, str):
                # compatibilidade: linhas "☐ titulo" / "☑ titulo" / "titulo"
                s = item.strip()
                if not s:
                    continue
                concluido = s.startswith("☑")
                if s.startswith("☐") or s.startswith("☑"):
                    titulo = s[2:].strip()
                else:
                    titulo = s
                if titulo:
                    livros.append({"id": 0, "titulo": titulo, "concluido": concluido})

    # Desejos esperados: {id:int, titulo:str}
    if isinstance(desejos_in, list):
        for item in desejos_in:
            if isinstance(item, dict):
                titulo = str(item.get("titulo", "")).strip()
                if not titulo:
                    continue
                desejos.append({
                    "id": int(item.get("id", 0)) if str(item.get("id", "")).isdigit() else 0,
                    "titulo": titulo
                })
            elif isinstance(item, str):
                s = item.strip()
                if not s:
                    continue
                if s.startswith("•"):
                    titulo = s[2:].strip()
                else:
                    titulo = s
                if titulo:
                    desejos.append({"id": 0, "titulo": titulo})

    # reatribuir IDs caso faltem/repitam
    used = set()
    cur = 1

    def fix_ids(arr):
        nonlocal cur
        for it in arr:
            _id = it.get("id", 0)
            if not isinstance(_id, int) or _id <= 0 or _id in used:
                while cur in used:
                    cur += 1
                it["id"] = cur
                used.add(cur)
                cur += 1
            else:
                used.add(_id)

    fix_ids(livros)
    fix_ids(desejos)

    return {"livros": livros, "desejos": desejos}


@app.get("/")
def index():
    q_livros = request.args.get("q_livros", "").strip().lower()
    q_desejos = request.args.get("q_desejos", "").strip().lower()

    data = load_data()
    ordenar_livros(data["livros"])

    livros = data["livros"]
    desejos = data["desejos"]

    if q_livros:
        livros = [x for x in livros if q_livros in x["titulo"].lower()]
    if q_desejos:
        desejos = [x for x in desejos if q_desejos in x["titulo"].lower()]

    a_ler = sum(1 for x in data["livros"] if not x.get("concluido", False))
    concluidos = sum(1 for x in data["livros"] if x.get("concluido", False))
    total_desejos = len(data["desejos"])
    total = a_ler + concluidos + total_desejos

    return render_template(
        "index.html",
        livros=livros,
        desejos=desejos,
        q_livros=request.args.get("q_livros", ""),
        q_desejos=request.args.get("q_desejos", ""),
        status={"a_ler": a_ler, "concluidos": concluidos, "desejos": total_desejos, "total": total},
    )


# ----------------------------
# EXPORTAR (download)
# ----------------------------
@app.get("/exportar")
def exportar():
    data = load_data()

    # opcional: incluir versão do ficheiro
    export_data = {"version": 1, "livros": data["livros"], "desejos": data["desejos"]}

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
    with open(tmp.name, "w", encoding="utf-8") as f:
        json.dump(export_data, f, ensure_ascii=False, indent=2)

    return send_file(
        tmp.name,
        as_attachment=True,
        download_name="biblioteca.json",
        mimetype="application/json",
    )


# ----------------------------
# IMPORTAR (upload)
# ----------------------------
@app.post("/importar")
def importar():
    file = request.files.get("ficheiro")
    if not file or not file.filename.lower().endswith(".json"):
        return redirect(url_for("index"))

    try:
        raw = json.load(file)
        # aceita {version, livros, desejos} ou {livros, desejos}
        if isinstance(raw, dict) and "version" in raw and ("livros" in raw or "desejos" in raw):
            # ok
            pass
        data = normalize_loaded_data(raw)
        save_data(data)
    except Exception:
        # se falhar, não altera nada
        pass

    return redirect(url_for("index"))


# ----------------------------
# Ações Livros / Desejos
# ----------------------------
@app.post("/livros/add")
def livros_add():
    titulo = request.form.get("titulo", "").strip()
    if titulo:
        data = load_data()
        if not any(x["titulo"].lower() == titulo.lower() for x in data["livros"]):
            data["livros"].append({"id": next_id(data), "titulo": titulo, "concluido": False})
            save_data(data)
    return redirect(url_for("index"))


@app.post("/desejos/add")
def desejos_add():
    titulo = request.form.get("titulo", "").strip()
    if titulo:
        data = load_data()
        if not any(x["titulo"].lower() == titulo.lower() for x in data["desejos"]):
            data["desejos"].append({"id": next_id(data), "titulo": titulo})
            save_data(data)
    return redirect(url_for("index"))


@app.post("/livros/toggle/<int:item_id>")
def livros_toggle(item_id):
    data = load_data()
    for x in data["livros"]:
        if x["id"] == item_id:
            x["concluido"] = not x.get("concluido", False)
            break
    save_data(data)
    return redirect(url_for("index"))


@app.post("/livros/delete/<int:item_id>")
def livros_delete(item_id):
    data = load_data()
    data["livros"] = [x for x in data["livros"] if x["id"] != item_id]
    save_data(data)
    return redirect(url_for("index"))


@app.post("/desejos/delete/<int:item_id>")
def desejos_delete(item_id):
    data = load_data()
    data["desejos"] = [x for x in data["desejos"] if x["id"] != item_id]
    save_data(data)
    return redirect(url_for("index"))


@app.post("/desejos/mover_para_livros/<int:item_id>")
def desejos_mover_para_livros(item_id):
    data = load_data()
    item = next((x for x in data["desejos"] if x["id"] == item_id), None)
    if item:
        data["desejos"] = [x for x in data["desejos"] if x["id"] != item_id]
        if not any(x["titulo"].lower() == item["titulo"].lower() for x in data["livros"]):
            data["livros"].append({"id": next_id(data), "titulo": item["titulo"], "concluido": False})
    save_data(data)
    return redirect(url_for("index"))


@app.post("/livros/mover_para_desejos/<int:item_id>")
def livros_mover_para_desejos(item_id):
    data = load_data()
    item = next((x for x in data["livros"] if x["id"] == item_id), None)
    if item:
        # regra: não mover se concluído
        if item.get("concluido", False):
            return redirect(url_for("index"))
        data["livros"] = [x for x in data["livros"] if x["id"] != item_id]
        if not any(x["titulo"].lower() == item["titulo"].lower() for x in data["desejos"]):
            data["desejos"].append({"id": next_id(data), "titulo": item["titulo"]})
    save_data(data)
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run
