import os
import time
import unicodedata

import noisereduce as nr
import numpy as np
import sounddevice as sd
from pydub import AudioSegment, effects
from playsound import playsound
import glob

for wav_file in glob.glob("*.wav"):
    os.remove(wav_file)

DURACION = 3  # segundos por palabra
PALABRAS = ["Feliz", "Jugo", "Mapa", "Ñandú", "Whisky", "Zanahoria"]
RESULTADOS = {}


# Normaliza texto para archivos y comparaciones
def normalizar_texto(texto):
    return unicodedata.normalize("NFKD", texto).encode("ASCII", "ignore").decode("utf-8").lower()


# Graba audio desde el micrófono
def grabar_audio(duracion, fs=44100):
    print(f"🎤 Grabando por {duracion} segundos...")
    audio = sd.rec(int(duracion * fs), samplerate=fs, channels=1, dtype="int16")
    sd.wait()
    return audio, fs


# Aplica reducción de ruido con IA (noisereduce)
def reducir_ruido(audio_np, fs):
    audio_np = audio_np.flatten()
    audio_float = audio_np.astype(np.float32)
    audio_denoised = nr.reduce_noise(y=audio_float, sr=fs)
    audio_int16 = np.int16(audio_denoised / np.max(np.abs(audio_denoised)) * 32767)
    return audio_int16


# Procesa, reduce ruido, normaliza y exporta
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

    audio_seg = effects.normalize(audio_seg)
    audio_seg += 6

    audio_seg.export(nombre_salida_mp3, format="mp3", bitrate="192k")


# Reproduce audio .mp3
def reproducir(nombre_mp3):
    print(f"🔊 Reproduciendo: {nombre_mp3}")
    playsound(nombre_mp3)


# Proceso principal
def ejecutar_prueba():
    for palabra in PALABRAS:
        intentos = 0
        texto = None
        nombre_archivo = normalizar_texto(palabra) + ".mp3"

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
    ejecutar_prueba()
