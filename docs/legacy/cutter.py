import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from moviepy.editor import VideoFileClip

# === Fonctions de découpage ===
def parcourir_video():
    # Correction du paramètre filetypes : tuple de motifs
    filepath = filedialog.askopenfilename(
        filetypes=[
            ("Fichiers vidéo", ("*.mp4", "*.mov", "*.avi")),
            ("Tous les fichiers", "*")
        ]
    )
    if filepath:
        entry_path.delete(0, tk.END)
        entry_path.insert(0, filepath)

# Fonction exécutée dans un thread pour ne pas bloquer l'UI
def process_decoupage(video_path, segment_duration, output_dir, progress_var, btn):
    try:
        video = VideoFileClip(video_path)
        video_duration = int(video.duration)
        os.makedirs(output_dir, exist_ok=True)

        total_segments = (video_duration + segment_duration - 1) // segment_duration
        for idx, start_time in enumerate(range(0, video_duration, segment_duration), start=1):
            end_time = min(start_time + segment_duration, video_duration)
            segment = video.subclip(start_time, end_time)
            segment_filename = os.path.join(output_dir, f"segment_{idx}.mp4")
            segment.write_videofile(segment_filename, codec="libx264", audio_codec="aac", verbose=False, logger=None)
            # Mise à jour de la barre de progression
            progress_var.set(int(idx / total_segments * 100))

        messagebox.showinfo("Succès", f"Découpage terminé !\nSegments dans : {output_dir}")
    except Exception as e:
        messagebox.showerror("Erreur", str(e))
    finally:
        btn.config(state=tk.NORMAL)
        progress_var.set(0)

# Callback du bouton
def lancer_decoupage():
    video_path = entry_path.get()
    if not os.path.exists(video_path):
        messagebox.showerror("Erreur", "Fichier vidéo introuvable.")
        return

    try:
        minutes = int(combo_duree.get())
        if minutes <= 0:
            raise ValueError
    except ValueError:
        messagebox.showerror("Erreur", "Veuillez choisir une durée valide.")
        return

    segment_duration = minutes * 60
    output_dir = os.path.join(os.path.dirname(video_path), "output_segments")

    # Désactiver le bouton pendant le traitement
    btn_lancer.config(state=tk.DISABLED)
    # Lancer le découpage dans un thread
    threading.Thread(target=process_decoupage, args=(video_path, segment_duration, output_dir, progress_var, btn_lancer), daemon=True).start()


# === Interface graphique améliorée ===
fenetre = tk.Tk()
fenetre.title("Découpeur de Vidéo")
fenetre.geometry("550x250")

# Chemin vidéo
tk.Label(fenetre, text="Chemin de la vidéo :").pack(pady=5)
entry_path = tk.Entry(fenetre, width=60)
entry_path.pack(pady=2)
tk.Button(fenetre, text="Parcourir", command=parcourir_video).pack(pady=2)

# Choix durée segment
tk.Label(fenetre, text="Durée par segment (minutes) :").pack(pady=5)
durations = ["1", "2", "5", "0.5"]  # options prédéfinies
combo_duree = ttk.Combobox(fenetre, values=durations, width=5)
combo_duree.set("2")
combo_duree.pack(pady=2)

# Barre de progression
progress_var = tk.IntVar()
progress = ttk.Progressbar(fenetre, orient="horizontal", length=400, mode="determinate", variable=progress_var)
progress.pack(pady=10)

# Bouton lancer
btn_lancer = tk.Button(fenetre, text="Lancer le découpage", command=lancer_decoupage)
btn_lancer.pack(pady=10)

# Placeholder pour futures fonctionnalités
frame_extra = tk.LabelFrame(fenetre, text="Fonctionnalités futures", padx=10, pady=10)
frame_extra.pack(fill="both", expand=True, padx=10, pady=5)
btn_subtitles = tk.Button(frame_extra, text="Ajouter sous-titres", state=tk.DISABLED)
btn_transcribe = tk.Button(frame_extra, text="Transcription audio", state=tk.DISABLED)
btn_subtitles.grid(row=0, column=0, padx=5, pady=5)
btn_transcribe.grid(row=0, column=1, padx=5, pady=5)

fenetre.mainloop()
