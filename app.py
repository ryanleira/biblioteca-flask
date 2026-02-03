from flask import Flask, render_template, request, redirect, url_for, send_file, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, login_user, login_required, logout_user, current_user, UserMixin
)
from werkzeug.security import generate_password_hash, check_password_hash
import tempfile
import json
import os

app = Flask(__name__)
app.config["SECRET_KEY"] = "troca-isto-por-uma-chave-secreta"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///biblioteca.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

login_manager = LoginManager(app)
login_manager.login_view = "login"  # para onde vai quando não está logado


# -----------------------
# Modelos (BD)
# -----------------------
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)


class Livro(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(200), nullable=False)
    concluido = db.Column(db.Boolean, default=False, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)


class Desejo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(200), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# cria tabelas na 1ª execução
with app.app_context():
    db.create_all()


def ordenar_livros(livros):
    # ☐ primeiro, ☑ depois, alfabético
    return sorted(livros, key=lambda x: (1 if x.concluido else 0, x.titulo.strip().lower()))


# -----------------------
# Auth (Login/Registo)
# -----------------------
@app.get("/registar")
def registar():
    return render_template("registar.html")


@app.post("/registar")
def registar_post():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "").strip()

    if not username or not password:
        flash("Preenche utilizador e password.")
        return redirect(url_for("registar"))

    if User.query.filter_by(username=username).first():
        flash("Esse utilizador já existe.")
        return redirect(url_for("registar"))

    user = User(
        username=username,
        password_hash=generate_password_hash(password)
    )
    db.session.add(user)
    db.session.commit()

    flash("Conta criada! Faz login.")
    return redirect(url_for("login"))


@app.get("/login")
def login():
    return render_template("login.html")


@app.post("/login")
def login_post():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "").strip()

    user = User.query.filter_by(username=username).first()
    if not user or not check_password_hash(user.password_hash, password):
        flash("Utilizador ou password incorretos.")
        return redirect(url_for("login"))

    login_user(user)
    return redirect(url_for("index"))


@app.post("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


# -----------------------
# App principal (por utilizador)
# -----------------------
@app.get("/")
@login_required
def index():
    q_livros = request.args.get("q_livros", "").strip().lower()
    q_desejos = request.args.get("q_desejos", "").strip().lower()

    livros = Livro.query.filter_by(user_id=current_user.id).all()
    desejos = Desejo.query.filter_by(user_id=current_user.id).all()

    livros = ordenar_livros(livros)

    if q_livros:
        livros = [x for x in livros if q_livros in x.titulo.lower()]
    if q_desejos:
        desejos = [x for x in desejos if q_desejos in x.titulo.lower()]

    a_ler = Livro.query.filter_by(user_id=current_user.id, concluido=False).count()
    concluidos = Livro.query.filter_by(user_id=current_user.id, concluido=True).count()
    total_desejos = Desejo.query.filter_by(user_id=current_user.id).count()
    total = a_ler + concluidos + total_desejos

    return render_template(
        "index.html",
        livros=livros,
        desejos=desejos,
        q_livros=request.args.get("q_livros", ""),
        q_desejos=request.args.get("q_desejos", ""),
        status={"a_ler": a_ler, "concluidos": concluidos, "desejos": total_desejos, "total": total},
        username=current_user.username
    )


@app.post("/livros/add")
@login_required
def livros_add():
    titulo = request.form.get("titulo", "").strip()
    if titulo:
        existe = Livro.query.filter_by(user_id=current_user.id, titulo=titulo).first()
        if not existe:
            db.session.add(Livro(titulo=titulo, concluido=False, user_id=current_user.id))
            db.session.commit()
    return redirect(url_for("index"))


@app.post("/desejos/add")
@login_required
def desejos_add():
    titulo = request.form.get("titulo", "").strip()
    if titulo:
        existe = Desejo.query.filter_by(user_id=current_user.id, titulo=titulo).first()
        if not existe:
            db.session.add(Desejo(titulo=titulo, user_id=current_user.id))
            db.session.commit()
    return redirect(url_for("index"))


@app.post("/livros/toggle/<int:item_id>")
@login_required
def livros_toggle(item_id):
    livro = Livro.query.filter_by(id=item_id, user_id=current_user.id).first_or_404()
    livro.concluido = not livro.concluido
    db.session.commit()
    return redirect(url_for("index"))


@app.post("/livros/delete/<int:item_id>")
@login_required
def livros_delete(item_id):
    livro = Livro.query.filter_by(id=item_id, user_id=current_user.id).first_or_404()
    db.session.delete(livro)
    db.session.commit()
    return redirect(url_for("index"))


@app.post("/desejos/delete/<int:item_id>")
@login_required
def desejos_delete(item_id):
    desejo = Desejo.query.filter_by(id=item_id, user_id=current_user.id).first_or_404()
    db.session.delete(desejo)
    db.session.commit()
    return redirect(url_for("index"))


@app.post("/desejos/mover_para_livros/<int:item_id>")
@login_required
def desejos_mover_para_livros(item_id):
    desejo = Desejo.query.filter_by(id=item_id, user_id=current_user.id).first_or_404()
    # remove desejo
    titulo = desejo.titulo
    db.session.delete(desejo)

    # cria livro se não existir
    existe = Livro.query.filter_by(user_id=current_user.id, titulo=titulo).first()
    if not existe:
        db.session.add(Livro(titulo=titulo, concluido=False, user_id=current_user.id))

    db.session.commit()
    return redirect(url_for("index"))


@app.post("/livros/mover_para_desejos/<int:item_id>")
@login_required
def livros_mover_para_desejos(item_id):
    livro = Livro.query.filter_by(id=item_id, user_id=current_user.id).first_or_404()

    if livro.concluido:
        # regra: não mover concluídos
        return redirect(url_for("index"))

    titulo = livro.titulo
    db.session.delete(livro)

    existe = Desejo.query.filter_by(user_id=current_user.id, titulo=titulo).first()
    if not existe:
        db.session.add(Desejo(titulo=titulo, user_id=current_user.id))

    db.session.commit()
    return redirect(url_for("index"))


# -----------------------
# Exportar/Importar POR UTILIZADOR
# -----------------------
@app.get("/exportar")
@login_required
def exportar():
    livros = Livro.query.filter_by(user_id=current_user.id).all()
    desejos = Desejo.query.filter_by(user_id=current_user.id).all()

    export_data = {
        "version": 1,
        "user": current_user.username,
        "livros": [{"titulo": x.titulo, "concluido": x.concluido} for x in livros],
        "desejos": [{"titulo": x.titulo} for x in desejos],
    }

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
    with open(tmp.name, "w", encoding="utf-8") as f:
        json.dump(export_data, f, ensure_ascii=False, indent=2)

    return send_file(
        tmp.name,
        as_attachment=True,
        download_name="biblioteca.json",
        mimetype="application/json",
    )


@app.post("/importar")
@login_required
def importar():
    file = request.files.get("ficheiro")
    if not file or not file.filename.lower().endswith(".json"):
        return redirect(url_for("index"))

    try:
        raw = json.load(file)
        livros_in = raw.get("livros", [])
        desejos_in = raw.get("desejos", [])

        # limpa dados do utilizador (ou muda para "mesclar", se preferires)
        Livro.query.filter_by(user_id=current_user.id).delete()
        Desejo.query.filter_by(user_id=current_user.id).delete()

        for it in livros_in:
            titulo = str(it.get("titulo", "")).strip()
            if titulo:
                db.session.add(Livro(
                    titulo=titulo,
                    concluido=bool(it.get("concluido", False)),
                    user_id=current_user.id
                ))

        for it in desejos_in:
            titulo = str(it.get("titulo", "")).strip()
            if titulo:
                db.session.add(Desejo(
                    titulo=titulo,
                    user_id=current_user.id
                ))

        db.session.commit()
    except Exception:
        pass

    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run()
