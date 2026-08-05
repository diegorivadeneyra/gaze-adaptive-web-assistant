from flask import Flask, request, jsonify
from flask_cors import CORS
from analyzers.text_analyzer import analyze_text
from analyzers.decision_engine import decide_action
from analyzers.image_analyzer import analyze_image

app = Flask(__name__)
CORS(app)

@app.route("/")
def home():
    return "Backend funcionando"

@app.route("/analyze", methods=["POST"])
def analyze():

    data = request.json
    content = data.get("content", "")
    content_type = data.get("content_type", "text")
    dwell_time = data.get("dwell_time", 0)

    if content_type == "text":
        analysis = analyze_text(content)
    elif content_type == "image":
        analysis = analyze_image(content)

    decision = decide_action(
        analysis["complexity"],
        analysis["needs_assistance"],
        dwell_time
    )

    print("\n===== DATOS RECIBIDOS =====")
    print("Dwell Time:", dwell_time)
    print("==========================\n")
    print("\n===== CONTENIDO OBSERVADO =====")
    print(content)
    print("\n===== ANALISIS =====")

    print("Concept:", analysis["concept"])

    print("Complexity:", analysis["complexity"])

    print("Needs Assistance:", analysis["needs_assistance"])

    print("====================\n")
    print("===============================\n")
    print("\n===== DECISION =====")
    print(decision)
    print("====================\n")

    return jsonify({
        "concept": analysis["concept"],
        "complexity": analysis["complexity"],
        "needs_assistance": analysis["needs_assistance"],
        "explanation": analysis["explanation"],
        "action": decision["action"]
    })

if __name__ == "__main__":
    app.run(debug=True)