import os
import time
import unicodedata
import numpy as np
import sounddevice as sd
import noisereduce as nr
from pydub import AudioSegment
from pydub.effects import compress_dynamic_range
from playsound import playsound

DURACION = 3  # segundos por palabra
PALABRAS = ["Feliz", "Jugo", "Mapa", "Ñandú", "Whisky", "Zanahoria"]
RESULTADOS = {}

CARPETA_USUARIO = "vos_usuario"
os.makedirs(CARPETA_USUARIO, exist_ok=True)

# Variable global para almacenar el índice del micrófono elegido
INDICE_MICROFONO = None


def normalizar_texto(texto):
    return unicodedata.normalize("NFKD", texto).encode("ASCII", "ignore").decode("utf-8").lower()


def seleccionar_microfono():
    dispositivos = sd.query_devices()
    dispositivos_entrada = [d for d in dispositivos if d['max_input_channels'] > 0]

    usar_predeterminado = input("\n¿Deseas usar el micrófono predeterminado? (S/n): ").strip().lower()

    if usar_predeterminado in ["", "s", "sí", "si"]:
        info = sd.query_devices(kind='input')
        print(f"🎤 Usando micrófono predeterminado: {info['name']}")
        return info['index']

    # Clasificamos los dispositivos
    externos = []
    internos = []

    for i, d in enumerate(dispositivos_entrada):
        nombre = d['name'].lower()
        if any(x in nombre for x in ["usb", "external", "bluetooth", "headset", "mic"]):
            externos.append((i, d))
        else:
            internos.append((i, d))

    print("\n🎧 Micrófonos externos:")
    for idx, (i, d) in enumerate(externos):
        print(f"  [{idx}] {d['name']}")

    print("\n💻 Micrófonos del sistema / integrados:")
    for idx, (i, d) in enumerate(internos):
        print(f"  [{idx + len( externos )}] {d['name']}")

    # Unimos ambas listas para selección por índice
    todos = externos + internos
    total = len(todos)

    while True:
        try:
            seleccion = int(input(f"\nSelecciona el número del micrófono a usar (0 - {total-1}): "))
            if 0 <= seleccion < total:
                seleccionado = todos[seleccion][0]  # índice real del dispositivo
                print(f"🎙️ Micrófono seleccionado: {todos[seleccion][1]['name']}")
                return seleccionado
        except ValueError:
            pass
        print("❌ Entrada inválida. Intenta nuevamente.")


def grabar_audio(duracion, fs=44100):
    global INDICE_MICROFONO
    print(f"🎤 Grabando por {duracion} segundos...")
    sd.default.device = (INDICE_MICROFONO, None)  # Forzar uso del micrófono elegido
    audio = sd.rec(int(duracion * fs), samplerate=fs, channels=1, dtype="int16")
    sd.wait()
    return audio, fs


def reducir_ruido(audio_np, fs):
    audio_np = audio_np.flatten()
    audio_float = audio_np.astype(np.float32)
    audio_denoised = nr.reduce_noise(y=audio_float, sr=fs, prop_decrease=0.5)
    audio_int16 = np.int16(audio_denoised / np.max(np.abs(audio_denoised)) * 32767)
    return audio_int16


def procesar_audio_numpy(audio_np, fs, nombre_salida_mp3):
    if os.path.exists(nombre_salida_mp3):
        try:
            os.remove(nombre_salida_mp3)
        except PermissionError:
            print(f"⚠️ No se puede sobrescribir {nombre_salida_mp3}, espera o cierra el reproductor.")
            time.sleep(1)
            os.remove(nombre_salida_mp3)

    audio_np = reducir_ruido(audio_np, fs)

    audio_seg = AudioSegment(
        audio_np.tobytes(),
        frame_rate=fs,
        sample_width=2,
        channels=1
    )

    # Aplicar compresión de rango dinámico leve
    audio_seg = compress_dynamic_range(audio_seg, threshold=-35.0, ratio=2.5)

    # Exportar con mayor bitrate
    audio_seg.export(nombre_salida_mp3, format="mp3", bitrate="256k")


def reproducir(nombre_mp3):
    print(f"🔊 Reproduciendo: {nombre_mp3}")
    playsound(nombre_mp3)


def ejecutar_prueba():
    for palabra in PALABRAS:
        intentos = 0
        texto = None
        nombre_archivo = os.path.join(CARPETA_USUARIO, normalizar_texto(palabra) + ".mp3")

        while not texto:
            print(f"\n🗣️ Pronuncia la palabra: {palabra}")
            audio_np, fs = grabar_audio(DURACION)
            procesar_audio_numpy(audio_np, fs, nombre_archivo)
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

    print("\n📄 Prueba completada. Resultados:")
    for palabra, datos in RESULTADOS.items():
        print(f"🔹 {palabra} grabada en {datos['intentos']} intento(s).")
        reproducir(datos["archivo_audio"])
        time.sleep(1)

    time.sleep(5)


if __name__ == "__main__":
    INDICE_MICROFONO = seleccionar_microfono()
    ejecutar_prueba()
