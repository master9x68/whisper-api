import os
import whisper
import speech_recognition as sr
from pydub import AudioSegment
from flask import Flask, request, jsonify
from ilovepdf import ILovePdf

app = Flask(__name__)

# Khởi tạo iLovePDF client với API key từ Environment Variables
PUBLIC_KEY = os.environ.get("ILOVE_PDF_PUBLIC_KEY")
SECRET_KEY = os.environ.get("ILOVE_PDF_SECRET_KEY")

ilovepdf = ILovePdf(public_key=PUBLIC_KEY, secret_key=SECRET_KEY)

def extract_segments_with_whisper(input_path):
    """
    Sử dụng Whisper để chuyển đổi âm thanh thành các đoạn văn bản có kèm thời gian.
    """
    model = whisper.load_model("base")
    result = model.transcribe(input_path, language="vi")
    segments = result['segments']
    return segments

def refine_segment_with_speech_recognition(audio_path, start_time, end_time):
    """
    Cải thiện chất lượng nhận diện bằng Google Speech Recognition.
    """
    recognizer = sr.Recognizer()
    audio = AudioSegment.from_file(audio_path)
    segment_audio = audio[start_time * 1000:end_time * 1000]
    segment_path = "temp_segment.wav"
    segment_audio.export(segment_path, format="wav")

    with sr.AudioFile(segment_path) as source:
        audio_data = recognizer.record(source)

    try:
        refined_text = recognizer.recognize_google(audio_data, language="vi-VN")
    except sr.UnknownValueError:
        refined_text = "Không thể nhận diện nội dung."
    except sr.RequestError as e:
        refined_text = f"Lỗi khi yêu cầu dịch vụ nhận diện: {e}"

    os.remove(segment_path)
    return refined_text

@app.route('/process', methods=['POST'])
def process_file():
    """
    Xử lý file audio/video, trích xuất văn bản bằng Whisper và cải thiện kết quả bằng Google Speech Recognition.
    """
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files['file']
    input_path = os.path.join('/tmp', file.filename)
    file.save(input_path)

    segments = extract_segments_with_whisper(input_path)
    result = []
    for segment in segments:
        start_time = segment['start']
        end_time = segment['end']
        whisper_text = segment['text'].strip()
        refined_text = refine_segment_with_speech_recognition(input_path, start_time, end_time)
        final_text = refined_text if refined_text != "Không thể nhận diện nội dung." else whisper_text
        result.append({"start": start_time, "end": end_time, "text": final_text})

    os.remove(input_path)
    return jsonify(result)

@app.route('/convert_to_pdf', methods=['POST'])
def convert_to_pdf():
    """
    Chuyển đổi file được upload sang PDF bằng iLovePDF API.
    """
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files['file']
    input_path = os.path.join('/tmp', file.filename)
    file.save(input_path)

    try:
        # Tạo công việc chuyển đổi sang PDF
        task = ilovepdf.new_task('officepdf')
        task.add_file(input_path)
        task.execute()
        output_path = task.download("/tmp")

        return jsonify({"message": "Conversion successful", "output_file": output_path})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/convert_from_pdf', methods=['POST'])
def convert_from_pdf():
    """
    Chuyển đổi PDF sang các định dạng khác bằng iLovePDF API.
    """
    if 'file' not in request.files or 'conversion_type' not in request.form:
        return jsonify({"error": "No file or conversion type provided"}), 400

    file = request.files['file']
    conversion_type = request.form['conversion_type']  # Loại chuyển đổi: 'pdfjpg', 'pdfword', 'pdfexcel', ...
    input_path = os.path.join('/tmp', file.filename)
    file.save(input_path)

    try:
        # Tạo công việc chuyển đổi từ PDF
        task = ilovepdf.new_task(conversion_type)
        task.add_file(input_path)
        task.execute()
        output_path = task.download("/tmp")

        return jsonify({"message": "Conversion successful", "output_file": output_path})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
