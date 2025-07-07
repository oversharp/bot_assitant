
import csv
import os
import psycopg2
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Token desde variables de entorno
TOKEN = os.getenv("BOT_TOKEN")

# Conexión a PostgreSQL desde Render
conn = psycopg2.connect(
    host=os.getenv("DB_HOST"),
    port=os.getenv("DB_PORT"),
    dbname=os.getenv("DB_NAME"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASS")
)
cursor = conn.cursor()

# Crear tabla si no existe
cursor.execute("""
CREATE TABLE IF NOT EXISTS gastos (
    id SERIAL PRIMARY KEY,
    nombre_usuario TEXT,
    categoria TEXT,
    monto REAL,
    descripcion TEXT,
    grupo_id BIGINT,
    fecha TEXT
)
""")
conn.commit()

# Cargar presupuesto desde CSV
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

# Comandos
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Hola, soy tu bot de gastos. Usa /gasto para registrar un gasto.")

async def gasto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        monto = float(context.args[0])
        categoria = context.args[1].lower()
        if categoria == "ahorro":
            await update.message.reply_text("⚠️ Usa /ahorro para registrar aportes a la categoría de ahorro.")
            return
        if categoria not in presupuestos:
            await update.message.reply_text("❌ Categoría no válida.")
            return
        descripcion = ' '.join(context.args[2:]) or "-"
        nombre_usuario = update.effective_user.first_name
        grupo = update.effective_chat.id
        fecha = datetime.utcnow().isoformat()
        cursor.execute("INSERT INTO gastos (nombre_usuario, categoria, monto, descripcion, grupo_id, fecha) VALUES (%s, %s, %s, %s, %s, %s)",
               (nombre_usuario, categoria, monto, descripcion, grupo, fecha))
        conn.commit()
        await update.message.reply_text(f"✅ Gasto registrado: ${monto} en *{categoria}* ({descripcion})", parse_mode="Markdown")
    except:
        await update.message.reply_text("❌ Uso: /gasto <monto> <categoría> <descripción opcional>")

async def ahorro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        monto = float(context.args[0])
        descripcion = ' '.join(context.args[1:]) or "-"
        nombre_usuario = update.effective_user.first_name
        grupo = update.effective_chat.id
        fecha = datetime.utcnow().isoformat()
        cursor.execute("INSERT INTO gastos (nombre_usuario, categoria, monto, descripcion, grupo_id, fecha) VALUES (%s, %s, %s, %s, %s, %s)",
                       (nombre_usuario, "ahorro", monto, descripcion, grupo, fecha))
        conn.commit()
        await update.message.reply_text(f"💰 Aporte registrado: ${monto} a *ahorro* ({descripcion})", parse_mode="Markdown")
    except:
        await update.message.reply_text("❌ Uso: /ahorro <monto> <descripción opcional>")

async def resumen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    grupo = update.effective_chat.id
    cursor.execute("SELECT categoria, SUM(monto) FROM gastos WHERE grupo_id=%s GROUP BY categoria", (grupo,))
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
    inicio_semana = hoy - timedelta(days=hoy.weekday())
    inicio_mes = hoy.replace(day=1)
    grupo = update.effective_chat.id
    cursor.execute("SELECT categoria, monto, fecha FROM gastos WHERE grupo_id=%s", (grupo,))
    gastos_categoria = {cat: {"semanal": 0, "mensual": 0} for cat in presupuestos}
    for cat, monto, fecha_str in cursor.fetchall():
        fecha = datetime.fromisoformat(fecha_str).date()
        if fecha >= inicio_semana:
            gastos_categoria[cat]["semanal"] += monto
        if fecha >= inicio_mes:
            gastos_categoria[cat]["mensual"] += monto
    msg = "📊 *Reporte Semanal/Mensual:*/n"
    for cat, pres in presupuestos.items():
        g = gastos_categoria[cat]
        if pres["semanal"] is not None:
            msg += f"• {cat} (S): ${pres['semanal'] - g['semanal']:.2f} / ${pres['semanal']:.2f}/n"
        elif pres["mensual"] is not None:
            msg += f"• {cat} (M): ${pres['mensual'] - g['mensual']:.2f} / ${pres['mensual']:.2f}/n"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def reporte_anual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    inicio_ano = datetime.utcnow().replace(month=1, day=1).date()
    grupo = update.effective_chat.id
    cursor.execute("SELECT categoria, monto, fecha FROM gastos WHERE grupo_id=%s", (grupo,))
    gastos_totales = {}
    for cat, monto, fecha_str in cursor.fetchall():
        if cat not in presupuestos:
            continue
        fecha = datetime.fromisoformat(fecha_str).date()
        if fecha >= inicio_ano:
            gastos_totales[cat] = gastos_totales.get(cat, 0) + monto
    msg = "📅 *Reporte Anual:*/n"
    for cat, pres in presupuestos.items():
        if pres["anual"] is None:
            continue
        gasto = gastos_totales.get(cat, 0)
        restante = pres["anual"] - gasto
        msg += f"• {cat}: ${restante:.2f} / ${pres['anual']:.2f}/n"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def historial(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        fecha_ini = datetime.fromisoformat(context.args[0]).date()
        fecha_fin = datetime.fromisoformat(context.args[1]).date()
    except:
        await update.message.reply_text("❌ Uso correcto: /historial YYYY-MM-DD YYYY-MM-DD")
        return
    grupo = update.effective_chat.id
    cursor.execute("SELECT fecha, categoria, monto, descripcion, nombre_usuario FROM gastos WHERE grupo_id=%s AND fecha BETWEEN %s AND %s ORDER BY fecha ASC", (grupo, fecha_ini, fecha_fin))
    filas = cursor.fetchall()
    if not filas:
        await update.message.reply_text("No hay gastos en ese rango.")
        return
    msg = f"🧾 *Historial de gastos del {fecha_ini} al {fecha_fin}:*/n"
    for fecha, cat, monto, desc, user in filas:
        msg += f"{fecha} - ${monto:.2f} - {cat} ({desc}) - *{user}*/n"
    await update.message.reply_text(msg, parse_mode="Markdown")

# Inicialización del bot
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("gasto", gasto))
app.add_handler(CommandHandler("ahorro", ahorro))
app.add_handler(CommandHandler("resumen", resumen))
app.add_handler(CommandHandler("reporte", reporte))
app.add_handler(CommandHandler("reporte_anual", reporte_anual))
app.add_handler(CommandHandler("historial", historial))
app.run_polling()
