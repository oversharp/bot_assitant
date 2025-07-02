import csv
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import sqlite3
import os
import psycopg2

TOKEN = os.getenv("BOT_TOKEN")  # Se obtiene desde las variables de entorno

# Conexión a la base de datos
conn = psycopg2.connect(
    host=os.getenv("DB_HOST"),
    port=os.getenv("DB_PORT"),
    dbname=os.getenv("DB_NAME"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASS")
)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS gastos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user TEXT,
    categoria TEXT,
    monto REAL,
    descripcion TEXT,
    grupo_id INTEGER,
    fecha TEXT
)
""")

conn.commit()

# Carga de presupuesto
def cargar_presupuestos():
    presupuestos = {}
    with open("presupuesto_config.csv", newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            cat = row["categoria"].lower()
            presupuestos[cat] = {
                "semanal": float(row["semanal"]) if row["semanal"] else None,
                "mensual": float(row["mensual"]) if row["mensual"] else None,
                "anual": float(row["anual"]) if row["anual"] else None,
            }
    return presupuestos

presupuestos = cargar_presupuestos()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Hola, soy tu bot de gastos. Usa /gasto para registrar un gasto.")

async def gasto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        monto = float(context.args[0])
        categoria = context.args[1].lower()
        descripcion = ' '.join(context.args[2:]) or "-"
        user = update.effective_user.first_name
        grupo = update.effective_chat.id
        fecha = datetime.utcnow().isoformat()
        cursor.execute("INSERT INTO gastos (user, categoria, monto, descripcion, grupo_id) VALUES (?, ?, ?, ?, ?)",
                       (user, categoria, monto, descripcion, grupo, fecha))
        conn.commit()

        await update.message.reply_text(f"✅ Gasto registrado: ${monto} en *{categoria}* ({descripcion})", parse_mode="Markdown")
    except:
        await update.message.reply_text("❌ Uso: /gasto <monto> <categoría> <descripción opcional>")

async def resumen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    grupo = update.effective_chat.id
    cursor.execute("SELECT categoria, SUM(monto) FROM gastos WHERE grupo_id=? GROUP BY categoria", (grupo,))
    datos = cursor.fetchall()
    if datos:
        msg = "📊 *Resumen de gastos por categoría:*\n"
        for cat, total in datos:
            msg += f"• {cat}: ${total:.2f}\n"
        await update.message.reply_text(msg, parse_mode="Markdown")
    else:
        await update.message.reply_text("No hay gastos registrados aún.")

async def reporte(update: Update, context: ContextTypes.DEFAULT_TYPE):
    hoy = datetime.utcnow().date()
    inicio_semana = hoy - timedelta(days=hoy.weekday())  # lunes
    inicio_mes = hoy.replace(day=1)

    grupo = update.effective_chat.id
    cursor.execute("SELECT categoria, SUM(monto), fecha FROM gastos WHERE grupo_id=? GROUP BY categoria", (grupo,))
    gastos_categoria = {}
    for cat in presupuestos:
        gastos_categoria[cat] = {"semanal": 0, "mensual": 0}

    cursor.execute("SELECT categoria, monto, descripcion, user, ROWID, fecha FROM gastos WHERE grupo_id=?", (grupo,))
    for row in cursor.fetchall():
        cat, monto, *_ = row
        if cat in gastos_categoria:
            cursor.execute("SELECT fecha FROM gastos WHERE ROWID=?", (row[4],))
            fecha_str = cursor.fetchone()[0]
            fecha = datetime.fromisoformat(fecha_str).date() if fecha_str else hoy
            if fecha >= inicio_semana:
                gastos_categoria[cat]["semanal"] += monto
            if fecha >= inicio_mes:
                gastos_categoria[cat]["mensual"] += monto

    msg = "📊 *Reporte Semanal/Mensual:*\n"
    for cat, pres in presupuestos.items():
        semanal = pres["semanal"]
        mensual = pres["mensual"]
        g = gastos_categoria[cat]
        if semanal is not None:
            msg += f"• {cat} (S): ${semanal - g['semanal']:.2f} / ${semanal:.2f}\n"
        elif mensual is not None:
            msg += f"• {cat} (M): ${mensual - g['mensual']:.2f} / ${mensual:.2f}\n"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def reporte_anual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    inicio_ano = datetime.utcnow().replace(month=1, day=1).date()
    grupo = update.effective_chat.id
    cursor.execute("SELECT categoria, monto, fecha FROM gastos WHERE grupo_id=?", (grupo,))
    gastos_acum = {}
    for row in cursor.fetchall():
        cat, monto, fecha_str = row
        if cat not in presupuestos:
            continue
        fecha = datetime.fromisoformat(fecha_str).date() if fecha_str else inicio_ano
        if fecha >= inicio_ano:
            gastos_acum[cat] = gastos_acum.get(cat, 0) + monto

    msg = "📅 *Reporte Anual:*\n"
    for cat, pres in presupuestos.items():
        if pres["anual"] is None:
            continue
        gasto = gastos_acum.get(cat, 0)
        restante = pres["anual"] - gasto
        msg += f"• {cat}: ${restante:.2f} / ${pres['anual']:.2f}\n"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def historial(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        fecha_ini = datetime.fromisoformat(context.args[0]).date()
        fecha_fin = datetime.fromisoformat(context.args[1]).date()
    except:
        await update.message.reply_text("❌ Uso correcto: /historial YYYY-MM-DD YYYY-MM-DD")
        return

    grupo = update.effective_chat.id
    cursor.execute("""
    SELECT fecha, categoria, monto, descripcion, user 
    FROM gastos 
    WHERE grupo_id=? AND fecha BETWEEN ? AND ?
    ORDER BY fecha ASC
    """, (grupo, fecha_ini, fecha_fin))

    filas = cursor.fetchall()
    if not filas:
        await update.message.reply_text("No hay gastos en ese rango.")
        return

    msg = f"🧾 *Historial de gastos del {fecha_ini} al {fecha_fin}:*\n"
    for f in filas:
        fecha, cat, monto, desc, user = f
        msg += f"{fecha} - ${monto:.2f} - {cat} ({desc}) - *{user}*\n"
    await update.message.reply_text(msg, parse_mode="Markdown")



app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("gasto", gasto))
app.add_handler(CommandHandler("resumen", resumen))
app.add_handler(CommandHandler("reporte", reporte))
app.add_handler(CommandHandler("reporte_anual", reporte_anual))
app.add_handler(CommandHandler("historial", historial))
app.run_polling()
