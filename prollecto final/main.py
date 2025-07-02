import os
import time
import unicodedata
import numpy as np
import sounddevice as sd
import noisereduce as nr
from pydub import AudioSegment
from pydub.effects import compress_dynamic_range
from playsound import playsound
from pydub.silence import detect_nonsilent  # 🟨 Para detectar silencios y fragmentos con voz

# ===============================
# 🔧 PARÁMETROS Y CONFIGURACIÓN
# ===============================
DURACION = 3  # ⏱ Tiempo de grabación por palabra (segundos)
PALABRAS = ["Feliz", "Jugo", "Mapa", "Ñandú", "Whisky", "Zanahoria"]  # 📚 Lista de palabras para grabar
RESULTADOS = {}

# 🗂️ Carpetas donde se guardan los audios generados
CARPETA_USUARIO = "vos_usuario"
CARPETA_ORIGINAL = os.path.join(CARPETA_USUARIO, "audio_orijinal")   # 🎙️ Audios originales grabados
CARPETA_MEJORADO = os.path.join(CARPETA_USUARIO, "mejorado")        # audio mejorado
CARPETA_PALABRAS = os.path.join(CARPETA_USUARIO, "palabras")         # 🔉 Audios procesados (limpios)
CARPETA_LETRAS = os.path.join(CARPETA_USUARIO, "letras")             # 🔠 Fragmentos cortados (letras)

# 🛠️ Crear las carpetas necesarias si no existen
os.makedirs(CARPETA_USUARIO, exist_ok=True)
os.makedirs(CARPETA_ORIGINAL, exist_ok=True)
os.makedirs(CARPETA_PALABRAS, exist_ok=True)
os.makedirs(CARPETA_LETRAS, exist_ok=True)
os.makedirs(CARPETA_MEJORADO, exist_ok=True)

# Variables globales
INDICE_MICROFONO = None
FREQ_MUESTREO = None

# ===============================
# 🔠 UTILIDAD: NORMALIZAR TEXTO
# ===============================
def normalizar_texto(texto):
    """🔤 Elimina tildes y convierte texto a minúsculas para facilitar la comparación."""
    return unicodedata.normalize("NFKD", texto).encode("ASCII", "ignore").decode("utf-8").lower()

# ===============================
# 🎙️ DETECCIÓN DE MICRÓFONOS DISPONIBLES
# ===============================
def detectar_micros_filtrados():
    """
    🔍 Escanea todos los dispositivos de entrada disponibles y los clasifica en 4 grupos:
        🔌 cable: dispositivos conectados físicamente (USB, jack)
        📶 bluetooth: micrófonos inalámbricos
        💻 otros_externos: webcam, arrays, etc.
        🎵 audio_sistema: mezcla estéreo o loopback del sistema
    Solo se agregan los dispositivos que pueden abrirse correctamente con su sample rate.
    """

    dispositivos = sd.query_devices()  # 📥 Obtener todos los dispositivos disponibles
    cable = []             # 🔌 Lista de micrófonos por cable
    bluetooth = []         # 📶 Lista de micrófonos Bluetooth
    otros_externos = []    # 💻 Lista de otros micrófonos externos
    audio_sistema = []     # 🎵 Mezcla estéreo y entradas del sistema

    print("\n🔍 Escaneando dispositivos de entrada...")

    # 🧠 Palabras clave para clasificar los dispositivos por tipo (según nombre)
    claves_sistema = ["mezcla estéreo", "stereo mix", "loopback", "what u hear", "input stereo", "wave out"]
    claves_cable = ["usb", "wired", "jack", "external", "codec"]
    claves_bluetooth = ["bluetooth", "bt", "airpods", "wireless"]
    claves_otros = ["webcam", "camera", "microphone array"]

    for i, d in enumerate(dispositivos):
        if d['max_input_channels'] < 1:
            continue  # ⚠️ Ignorar si no tiene canales de entrada

        nombre = d['name'].lower()
        fs = int(d['default_samplerate'])  # 🎚️ Frecuencia de muestreo

        # 🔍 Clasificar el dispositivo según su nombre
        if any(k in nombre for k in claves_sistema):
            tipo = "sistema"
        elif any(k in nombre for k in claves_bluetooth):
            tipo = "bluetooth"
        elif any(k in nombre for k in claves_cable):
            tipo = "cable"
        elif any(k in nombre for k in claves_otros):
            tipo = "otros"
        else:
            tipo = "otros"

        # ✅ Probar si se puede abrir el dispositivo
        try:
            with sd.InputStream(device=i, channels=1, samplerate=fs):
                if tipo == "sistema":
                    audio_sistema.append((i, d, fs))
                    print(f"✅ AUDIO DEL SISTEMA válido: {d['name']}")
                elif tipo == "bluetooth":
                    bluetooth.append((i, d, fs))
                    print(f"✅ BLUETOOTH válido: {d['name']}")
                elif tipo == "cable":
                    cable.append((i, d, fs))
                    print(f"✅ CABLE válido: {d['name']}")
                else:
                    otros_externos.append((i, d, fs))
                    print(f"✅ OTRO válido: {d['name']}")

        # ⚠️ Si el dispositivo no puede abrirse
        except Exception as e:
            if tipo == "sistema":
                audio_sistema.append((i, d, fs, False))
                print(f"⚠️ AUDIO DEL SISTEMA detectado pero no usable: {d['name']} ({e})")
            else:
                print(f"❌ Rechazado: {d['name']} ({e})")

    # 🔁 Retornar los 4 grupos
    return cable, bluetooth, otros_externos, audio_sistema


# ===============================
# 🎚️ SELECCIÓN DEL MICRÓFONO A UTILIZAR
# ===============================
def seleccionar_microfono():
    """
    🎛 Permite al usuario elegir entre:
        - el micrófono predeterminado del sistema
        - o uno específico de entre los detectados por tipo.
    ✅ Solo se muestran dispositivos previamente validados como funcionales.
    """

    # 📋 Obtener listas de micrófonos válidos
    cable, bluetooth, otros, sistema = detectar_micros_filtrados()
    todos = cable + bluetooth + otros + [s[:3] for s in sistema if len(s) == 3]  # Solo válidos

    if not todos:
        print("❌ No se encontraron dispositivos válidos.")
        exit()

    # 🤔 Preguntar al usuario si quiere usar el predeterminado
    usar_predeterminado = input("\n¿Deseas usar el micrófono predeterminado? (S/n): ").strip().lower()
    if usar_predeterminado in ["", "s", "sí", "si"]:
        info = sd.query_devices(kind='input')
        fs = int(info['default_samplerate'])
        print(f"🎤 Usando micrófono predeterminado: {info['name']} ({fs} Hz)")
        return info['index'], fs

    # ===============================
    # 🧾 Mostrar lista de dispositivos por tipo
    # ===============================

    print("\n🔌 Micrófonos por cable:")
    for idx, (i, d, fs) in enumerate(cable):
        print(f"  [{idx}] {d['name']} ({fs} Hz)")

    print("\n📶 Micrófonos Bluetooth:")
    for idx, (i, d, fs) in enumerate(bluetooth):
        print(f"  [{idx + len(cable)}] {d['name']} ({fs} Hz)")

    print("\n💻 Otros micrófonos externos:")
    for idx, (i, d, fs) in enumerate(otros):
        print(f"  [{idx + len(cable) + len(bluetooth)}] {d['name']} ({fs} Hz)")

    print("\n🎵 Audio del sistema (Mezcla estéreo, etc.):")
    for idx, entrada in enumerate(sistema):
        i, d, fs = entrada[:3]
        usable = len(entrada) == 3
        tag = "✅" if usable else "❌ NO USABLE"
        print(f"  [{idx + len(cable) + len(bluetooth) + len(otros)}] {d['name']} ({fs} Hz) {tag}")

    # ===============================
    # 🎯 Selección manual del dispositivo
    # ===============================
    while True:
        try:
            seleccion = int(input(f"\nSelecciona el número del dispositivo a usar (0 - {len(todos)-1}): "))
            if 0 <= seleccion < len(todos):
                i_real, d, fs = todos[seleccion]
                print(f"🎙️ Dispositivo seleccionado: {d['name']} ({fs} Hz)")
                return i_real, fs
        except ValueError:
            pass
        print("❌ Entrada inválida. Intenta nuevamente.")

# ===============================
# 🔴 GRABACIÓN DE AUDIO
# ===============================
def grabar_audio(duracion):
    """🎤 Graba audio desde el micrófono seleccionado."""
    sd.default.device = (INDICE_MICROFONO, None)
    audio = sd.rec(int(duracion * FREQ_MUESTREO), samplerate=FREQ_MUESTREO, channels=1, dtype="int16")
    sd.wait()
    return audio, FREQ_MUESTREO

# ===============================
# 🌫️ REDUCCIÓN DE RUIDO
# ===============================
def reducir_ruido(audio_np, fs):
    """🔇 Aplica reducción de ruido al audio grabado."""
    audio_np = audio_np.flatten()
    audio_float = audio_np.astype(np.float32)
    audio_denoised = nr.reduce_noise(y=audio_float, sr=fs, prop_decrease=0.5)
    audio_int16 = np.int16(audio_denoised / np.max(np.abs(audio_denoised)) * 32767)
    return audio_int16

# ===============================
# 🔁 PROCESAMIENTO COMPLETO
# ===============================
def procesar_audio_numpy(audio_np, fs, nombre_original_base):
    """
    ✳️ Guarda el audio original, reduce ruido, guarda el limpio,
        y extrae letras en subcarpetas específicas.
    """
    ruta_original = os.path.join(CARPETA_ORIGINAL, nombre_original_base + ".mp3")
    ruta_mejorado = os.path.join(CARPETA_MEJORADO, nombre_original_base + ".mp3")

    # 🟨 Exportar audio original sin procesar
    audio_seg_original = AudioSegment(audio_np.tobytes(), frame_rate=fs, sample_width=2, channels=1)
    if os.path.exists(ruta_original):
        os.remove(ruta_original)
    audio_seg_original.export(ruta_original, format="mp3", bitrate="256k")
    print(f"📥 Audio original guardado en: {ruta_original}")

    # 🟦 Reducción de ruido
    audio_np = reducir_ruido(audio_np, fs)

    # 🟦 Crear audio limpio y exportarlo
    audio_seg = AudioSegment(audio_np.tobytes(), frame_rate=fs, sample_width=2, channels=1)
    audio_seg = compress_dynamic_range(audio_seg, threshold=-35.0, ratio=2.5)
    if os.path.exists(ruta_mejorado):
        os.remove(ruta_mejorado)
    audio_seg.export(ruta_mejorado, format="mp3", bitrate="256k")
    print(f"📤 Audio limpio guardado en: {ruta_mejorado}")

    # 🟧 Extraer letras del audio limpio
    carpeta_subletras = os.path.join(CARPETA_LETRAS, nombre_original_base)
    letras_guardadas = extraer_letras(ruta_mejorado, carpeta_subletras)
    recortar_palabra_y_guardar(ruta_mejorado, umbral_silencio_db=audio_seg.dBFS - 20)

    return letras_guardadas

# ===============================
# 🔊 REPRODUCCIÓN DE AUDIO
# ===============================
def reproducir(nombre_mp3):
    """🔊 Reproduce un archivo de audio."""
    print(f"🎧 Reproduciendo: {nombre_mp3}")
    playsound(nombre_mp3)

# ===============================
# 🧪 PRUEBA COMPLETA DE PALABRAS
# ===============================
def ejecutar_prueba():
    """
    🔁 Para cada palabra:
        - se graba
        - se procesa
        - se reproduce
        - se verifican resultados
    """
    for palabra in PALABRAS:
        intentos = 0
        texto = None
        nombre_base = normalizar_texto(palabra)
        nombre_archivo = os.path.join(CARPETA_MEJORADO, nombre_base + ".mp3")

        while not texto:
            print(f"\n🗣️ Pronuncia la palabra: {palabra}")
            audio_np, fs = grabar_audio(DURACION)
            procesar_audio_numpy(audio_np, fs, nombre_base)
            reproducir(nombre_archivo)

            texto = input(f"✍️ ¿Qué palabra dijiste? (escribe para confirmar '{palabra}'): ").strip()
            intentos += 1

            if normalizar_texto(texto) != normalizar_texto(palabra):
                print("❌ No coincide. Intenta nuevamente.")
                texto = None
            else:
                RESULTADOS[palabra] = {
                    "archivo_audio": nombre_archivo,
                    "intentos": intentos
                }
            time.sleep(1)

    print("\n📋 Prueba completada. Resultados:")
    for palabra, datos in RESULTADOS.items():
        print(f"🔹 {palabra} grabada en {datos['intentos']} intento(s).")
        reproducir(datos["archivo_audio"])
        time.sleep(1)

# ===============================
# ✂️ CORTAR LETRAS DESDE AUDIO
# ===============================
def extraer_letras(audio_path, carpeta_salida, margen_silencio=60, umbral_relativo_db=20, unir_cercanos_ms=150):
    """
    🔠 Extrae letras (fragmentos con voz) del audio limpio
    y las guarda en subcarpeta de la palabra correspondiente.
    """
    audio = AudioSegment.from_file(audio_path, format="mp3")
    umbral_dinamico = audio.dBFS - umbral_relativo_db
    print(f"📉 Umbral de detección: {umbral_dinamico:.2f} dBFS")

    segmentos = detect_nonsilent(audio, min_silence_len=margen_silencio, silence_thresh=umbral_dinamico)
    if not segmentos:
        print(f"⚠️ No se detectaron fragmentos en: {audio_path}")
        return []

    # Unir fragmentos cercanos
    combinados = [segmentos[0]]
    for actual in segmentos[1:]:
        anterior = combinados[-1]
        if actual[0] - anterior[1] < unir_cercanos_ms:
            combinados[-1] = [anterior[0], actual[1]]
        else:
            combinados.append(actual)

    # Crear carpeta específica para esa palabra
    os.makedirs(carpeta_salida, exist_ok=True)
    base = os.path.splitext(os.path.basename(audio_path))[0]
    archivos = []

    for idx, (inicio, fin) in enumerate(combinados):
        fragmento = audio[inicio:fin]
        if len(fragmento) < 80:
            continue  # Ignora fragmentos muy cortos

        # ✂️ Recortar silencios del fragmento
        fragmento = recortar_silencio_fragmento(fragmento, umbral_silencio_db=umbral_dinamico)

        if len(fragmento) < 80:
            continue  # Revalidar después de recortar
        
    nombre = os.path.join(carpeta_salida, f"{base}_letra_{idx+1}.mp3")
    fragmento.export(nombre, format="mp3")
    archivos.append(nombre)
    print(f"🔠 Fragmento guardado: {nombre}")

    return archivos
def recortar_silencio_fragmento(fragmento, umbral_silencio_db=-40, margen=10):
    dur = len(fragmento)
    inicio = 0
    fin = dur
    for i in range(dur):
        if fragmento[i:i+1].dBFS > umbral_silencio_db:
            inicio = max(0, i - margen)
            break
    for i in range(dur - 1, 0, -1):
        if fragmento[i-1:i].dBFS > umbral_silencio_db:
            fin = min(dur, i + margen)
            break
    return fragmento[inicio:fin]

# ✂️ Recorta la palabra entera desde un archivo .mp3 y la guarda
def recortar_palabra_y_guardar(audio_path, umbral_silencio_db=-40):
    audio = AudioSegment.from_file(audio_path, format="mp3")
    audio_recortado = recortar_silencio_fragmento(audio, umbral_silencio_db)
    base = os.path.splitext(os.path.basename(audio_path))[0]
    salida = os.path.join(CARPETA_PALABRAS, f"{base}_recortado.mp3")
    audio_recortado.export(salida, format="mp3")
    print(f"📝 Palabra recortada exportada: {salida}")
# ===============================
# 🚀 EJECUCIÓN DEL PROGRAMA
# ===============================
if __name__ == "__main__":
    INDICE_MICROFONO, FREQ_MUESTREO = seleccionar_microfono()
    ejecutar_prueba()
