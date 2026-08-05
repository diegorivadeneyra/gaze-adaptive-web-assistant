from transformers import AutoProcessor
from transformers import AutoModelForVision2Seq
import torch
import requests
import json
from PIL import Image
from io import BytesIO

MODEL_NAME = "Qwen/Qwen2.5-VL-3B-Instruct"

print("Cargando Qwen VL...")

processor = AutoProcessor.from_pretrained(
    MODEL_NAME
)

model = AutoModelForVision2Seq.from_pretrained(
    MODEL_NAME,
    device_map="auto",
    torch_dtype=torch.float16
)

print("Qwen VL cargado.")

def analyze_image(image_path):

    print("\n===== IMAGE URL =====")
    print(image_path)
    print("=====================\n")

    response = requests.get(
        image_path,
        headers={
            "User-Agent": "Mozilla/5.0"
        },
        timeout=10
    )

    image = Image.open(
        BytesIO(response.content)
    )

    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image"
                },
                {
                    "type": "text",
                    "text": """
                Analyze this image.

                Return ONLY a valid JSON object.

                {
                    "concept": "main concept of the image",
                    "complexity": "Low, Medium or High",
                    "needs_assistance": true,
                    "explanation": "simple explanation for a student"
                }

                Do not add markdown.
                Do not add explanations outside the JSON.
                """
                }
            ]
        }
    ]

    text = processor.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True
    )

    inputs = processor(
        text=[text],
        images=[image],
        return_tensors="pt"
    )

    inputs = inputs.to(model.device)

    generated_ids = model.generate(
        **inputs,
        max_new_tokens=80
    )

    response = processor.batch_decode(
        generated_ids,
        skip_special_tokens=True
    )[0]
    
    print("\n===== QWEN RESPONSE =====")
    print(response)
    print("=========================\n")
    response = response.split("assistant")[-1].strip()

    try:

        analysis = json.loads(response)

        return analysis

    except Exception as e:

        print("JSON ERROR:", e)

        return {
            "concept": "Image Analysis Failed",
            "complexity": "Medium",
            "needs_assistance": True,
            "explanation": response
        }