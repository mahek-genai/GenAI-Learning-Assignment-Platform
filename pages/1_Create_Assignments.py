import json
import logging
import math
import random
import time
import base64
import os
from io import BytesIO

import boto3
import numpy as np
import streamlit as st
from PIL import Image
from botocore.exceptions import ClientError
from components.Parameter_store import S3_BUCKET_NAME

# =========================================================
# Logging
# =========================================================
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# =========================================================
# AWS Clients
# =========================================================
dynamodb_client = boto3.resource("dynamodb")
bedrock_client = boto3.client("bedrock-runtime")
questions_table = dynamodb_client.Table("assignments")
user_name = "CloudAge-User"

# =========================================================
# Model IDs
# =========================================================
text_model_id = "amazon.nova-pro-v1:0"
image_model_id = "amazon.nova-canvas-v1:0"

# =========================================================
# Session State Init
# =========================================================
if "question_answers" not in st.session_state:
    st.session_state["question_answers"] = None

if "is_generating" not in st.session_state:
    st.session_state["is_generating"] = False

if "last_request_time" not in st.session_state:
    st.session_state["last_request_time"] = 0

# =========================================================
# STRONG RETRY WRAPPER (Throttling Safe)
# =========================================================
def invoke_with_retry(client, **kwargs):
    retries = 6
    delay = 3

    for attempt in range(retries):
        try:
            response = client.invoke_model(**kwargs)

            # Small cooldown to prevent burst traffic
            time.sleep(1)

            return response

        except ClientError as e:
            error_code = e.response["Error"]["Code"]

            if error_code == "ThrottlingException":
                logger.warning(f"Throttled. Retrying in {delay} seconds...")
                time.sleep(delay)
                delay *= 2
            else:
                raise e

    raise Exception("Max retries exceeded due to throttling.")

# =========================================================
# TEXT MODEL CALL
# =========================================================
def query_generate_questions_answers_endpoint(input_text):

    prompt = (
        f"{input_text}\n"
        "Using the above context, generate five questions and answers.\n"
        "Return ONLY valid JSON list with keys: Id, Question, Answer."
    )

    input_data = {
        "inferenceConfig": {"max_new_tokens": 800},
        "messages": [
            {
                "role": "user",
                "content": [{"text": prompt}]
            }
        ]
    }

    response = invoke_with_retry(
        bedrock_client,
        modelId=text_model_id,
        body=json.dumps(input_data).encode("utf-8"),
        accept="application/json",
        contentType="application/json"
    )

    response_body = json.loads(response.get("body").read().decode())
    response_text = response_body["output"]["message"]["content"][0]["text"]

    cleaned = response_text.replace("```json", "").replace("```", "").strip()

    return json.loads(cleaned)

# =========================================================
# IMAGE MODEL CALL
# =========================================================
def query_generate_image_endpoint(input_text):

    input_body = json.dumps({
        "taskType": "TEXT_IMAGE",
        "textToImageParams": {
            "text": f"An image of {input_text}"
        },
        "imageGenerationConfig": {
            "numberOfImages": 1,
            "height": 512,
            "width": 512,
            "cfgScale": 7.5,
            "seed": np.random.randint(1000)
        }
    })

    response = invoke_with_retry(
        bedrock_client,
        body=input_body,
        modelId=image_model_id,
        accept="application/json",
        contentType="application/json"
    )

    response_body = json.loads(response.get("body").read())
    base64_image = response_body["images"][0]

    image_bytes = base64.b64decode(base64_image)
    image = Image.open(BytesIO(image_bytes))

    return image

# =========================================================
# Helper Functions
# =========================================================
def generate_assignment_id_key():
    epoch = round(time.time() * 1000)
    epoch = epoch - 1670000000000
    rand_id = math.floor(random.random() * 999)
    return str((epoch * 1000) + rand_id)


def load_file_to_s3(file_name, object_name):
    s3_client = boto3.client("s3")
    s3_client.upload_file(file_name, S3_BUCKET_NAME, object_name)


def insert_record_to_dynamodb(assignment_id, prompt, s3_image_name, data):
    questions_table.put_item(
        Item={
            "assignment_id": assignment_id,
            "teacher_id": user_name,
            "prompt": prompt,
            "s3_image_name": s3_image_name,
            "question_answers": data,
        }
    )

# =========================================================
# UI
# =========================================================
st.set_page_config(page_title="Create Assignments", page_icon=":pencil:", layout="wide")

st.sidebar.header("Create Assignments")
st.markdown("# Create Assignments")

text = st.text_area("Input Text")

# =========================================================
# Generate Questions Button
# =========================================================
if st.button("Generate Questions and Answers", disabled=st.session_state["is_generating"]):

    if not text:
        st.error("Please enter input text first!")

    else:
        # Cooldown control (minimum 3 sec between calls)
        current_time = time.time()
        if current_time - st.session_state["last_request_time"] < 3:
            st.warning("Please wait a few seconds before trying again.")
        else:
            st.session_state["is_generating"] = True
            st.session_state["last_request_time"] = current_time

            with st.spinner("Generating questions..."):
                try:
                    result = query_generate_questions_answers_endpoint(text)
                    st.session_state["question_answers"] = result
                except Exception as ex:
                    st.error(f"Error generating questions: {ex}")

            st.session_state["is_generating"] = False

# Display Questions
if st.session_state.get("question_answers"):
    st.markdown("## Generated Questions and Answers")
    st.text_area(
        "Questions and Answers",
        json.dumps(st.session_state["question_answers"], indent=4),
        height=320,
        label_visibility="collapsed"
    )

# =========================================================
# Generate Image Button
# =========================================================
st.button("Generate New Image")

if st.button("Generate New Image"):

    if not text:
        st.error("Please enter input text first!")

    else:
        with st.spinner("Generating image..."):
            try:
                image = query_generate_image_endpoint(text)
                image.save("temp-create.png")
                st.image(image, width=512)
            except Exception as ex:
                st.error(f"Error generating image: {ex}")

# =========================================================
# Save Assignment
# =========================================================
st.markdown("------------")

if st.button("Save Question"):

    if not st.session_state.get("question_answers"):
        st.error("Please generate questions first!")

    elif not text:
        st.error("Please enter input text first!")

    else:
        try:
            assignment_id = generate_assignment_id_key()
            questions_answers = json.dumps(st.session_state["question_answers"], indent=4)

            object_name = "no image created"

            if os.path.exists("temp-create.png"):
                object_name = f"generated_images/{assignment_id}.png"
                load_file_to_s3("temp-create.png", object_name)

            insert_record_to_dynamodb(
                assignment_id,
                text,
                object_name,
                questions_answers
            )

            st.success(f"Assignment saved successfully with ID: {assignment_id}")

        except Exception as ex:
            st.error(f"Error saving assignment: {ex}")
