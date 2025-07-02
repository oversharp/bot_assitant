from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import sqlite3
import os

TOKEN = os.getenv("8058970516:AHH_cWxF8RfJ52W8tyzIkzWonIo-Q4ZXx78")  # Se obtiene desde las variables de entorno

# Conexión a la base de datos
conn = sqlite3.connect("gastos.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS gastos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user TEXT,
    categoria TEXT,
    monto REAL,
    descripcion TEXT,
    grupo_id INTEGER
)
""")
conn.commit()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Hola, soy tu bot de gastos. Usa /gasto para registrar un gasto.")

async def gasto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        monto = float(context.args[0])
        categoria = context.args[1].lower()
        descripcion = ' '.join(context.args[2:]) or "-"
        user = update.effective_user.first_name
        grupo = update.effective_chat.id

        cursor.execute("INSERT INTO gastos (user, categoria, monto, descripcion, grupo_id) VALUES (?, ?, ?, ?, ?)",
                       (user, categoria, monto, descripcion, grupo))
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

app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("gasto", gasto))
app.add_handler(CommandHandler("resumen", resumen))

app.run_polling()
