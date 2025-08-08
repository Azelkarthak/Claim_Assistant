import os
import json
import random
import time
import re
from base64 import b64decode
import json
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from flask import Flask, request, jsonify, render_template, send_file
from model import get_ai_content
import html
import requests


# Create Flask app
app = Flask(__name__)


# @app.route('/ask', methods=['POST'])
# def ask():
#     data = request.get_json()
#     user_input = data.get("question", "")

#     if not user_input:
#         return jsonify({"error": "Question is required"}), 400

#     try:
#         print(f"User Input: {user_input}")
#         cleanRequest = clean_request_body(user_input)
#         response = generate_response(cleanRequest)
#         claimNumber = createClaim(response)
#         return jsonify(claimNumber)
#     except Exception as e:
#         return jsonify({"error": str(e)}), 500

# 


@app.route("/createClaim", methods=["POST"])
def create_claim():
    try:
        # Step 1: Get and clean HTML content
        html_content = request.get_data(as_text=True)
        print(f"HTML Content: {html_content}")
        soup = BeautifulSoup(html_content, "html.parser")
        plain_text = soup.get_text(separator=" ")
        decoded_text = html.unescape(plain_text)
        cleaned_text = re.sub(r'(\\n|/n|\n|\r)', ' ', decoded_text)
        cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip()

        # Step 2: Extract policy details
        policy_details, policy_number = extract_policy_details(cleaned_text)

        # Step 3: Retry logic for createClaim
        if policy_details is None:
            return jsonify({
                "claimNumber": "Claim Not Created, Invalid Policy Number",
                "policyNumber": policy_number,
                "message": "Policy Number is Invalid or Policy Does Not Exist"
            }), 400
        
        for attempt in range(3):
            print(f"Attempt {attempt + 1} to create claim...")

            # Always regenerate payload before attempt
            response_payload = generate_response(cleaned_text, policy_details)

            # Call createClaim API
            createClaimResponse = createClaim(response_payload)

            if createClaimResponse.status_code in [200, 201]:
                response_json = createClaimResponse.json()
                claim_number = response_json.get("claimNumber", "N/A")

                return jsonify({
                    "claimNumber": claim_number,
                    "policyNumber": policy_number,
                    "message": html_content                }), 200

        # If all 3 attempts fail
        return jsonify({
            "claimNumber": claim_number,
            "policyNumber": policy_number,
            "message": "Failed"
        }), createClaimResponse.status_code

    except Exception as e:
        return jsonify({
            "error": "Exception occurred during claim creation",
            "message": str(e),
            "policyNumber": policy_number if 'policy_number' in locals() else None
        }), 500


def generate_response(user_input, policy_details):
    # Load claim template
    with open('claim_template.json', 'r') as f:
        claim_template = json.load(f)


    print(f"Policy Details: {policy_details}")
    print(f"Claim Template: {claim_template}")

    prompt = f"""
You are a professional insurance claim assistant.

Your job is to extract structured data from the user's claim description and populate a valid claim creation JSON object.

---

📌 Master Data (use ONLY these values exactly):

ClaimantType:
- insured
- householdmember
- propertyowner
- customer
- employee
- other

PolicyType:
- BusinessOwners
- BusinessAuto
- CommercialPackage
- CommercialProperty
- farmowners
- GeneralLiability
- HOPHomeowners
- InlandMarine
- PersonalAuto
- travel_per
- PersonalUmbrella
- prof_liability
- WorkersComp
- D and 0

RelationshipToInsured:
- self
- agent
- attorney
- employee
- claimant
- claimantatty
- rentalrep
- repairshop
- other

LossCause:
- animal_bite
- burglary
- earthquake
- explosion
- fire
- glassbreakage
- hail
- hurricane
- vandalism
- mold
- riotandcivil
- snowice
- structfailure
- waterdamage
- wind

---

🧠 Context:

You will receive:
- A **free-text claim description** (from user or email).
- A **policy_details object** containing valid coverages.

---

📋 Instructions:

1. **Extract structured data** only when confidently inferable.
2. **Leave fields blank or omit them entirely** if data is missing or uncertain.
3. For `InvolvedVehicles`, add only if vehicle info (like VIN or plate) is present.
4. For each `InvolvedCoverage`:
   - Extract coverage **based on incident description** (e.g., "rear-ended" = Collision)
   -Find the matching coverage object from `policy_details['coverages']` where `"Coverage"` matches.
   - Use the corresponding `public id` from that object.
   - Only include if it's listed in the policy's coverages, if not then do not add the array also.
   - Include:
     - Coverage (e.g., "Collision", "Comprehensive")
     - CoverageType (extract from policy_details)
     - CoverageSubtype (same as CoverageType)
     - Claimant_FirstName
     - Claimant_LastName
     - ClaimantType

5. Determine:
   - `PolicyType` from policy context or description
   - `RelationshipToInsured` based on who is reporting (e.g., "I", "my friend")
   - `LossCause` from incident nature (choose from predefined list)

6. Date format for `LossDate` must be ISO 8601 with timezone offset, like:
   "2024-06-19T00:00:00+05:30"

7. If any field is not mentioned try to add it from the policy_details object.
   eg if addess is not mentioned in the claim description, try to add it from the policy_details object.
   eg if phone number is not mentioned in the claim description, try to add it from the policy_details object.
   eg if losscause are not mentioned in the claim description, keep the default value as glassbreakage.
8. Loss occured should be a string value, eg "Home"/"At Premises"/"At Work"/ "At Street"

---

🎯 Output:
Return only a valid, structured JSON object with human-readable formatting. No explanation text. Do not hallucinate missing details.

Claim Information:
{user_input}

Policy Details:
{policy_details}

---

🎯 Fill out the below template using only values inferred from the above:
{claim_template}
"""

    print(f"Prompt: {prompt}")
    response = get_ai_content(prompt)

    if not response:
        raise ValueError("Failed to get a valid response from the AI.")

    # Extract JSON from the AI response
    extracted_json = extract_json_from_response(response)

    print(json.dumps(extracted_json, indent=2))
    return extracted_json


# def get_ai_content(
#     prompt,
#     max_retries=3,
#     base_delay=2,
#     temperature=0.0,
#     top_p=0.95,
#     top_k=40,
#     minimum_output_tokens=2000
# ):
#     retry_count = 0

#     while retry_count <= max_retries:
#         try:
#             model = genai.GenerativeModel("gemini-2.0-flash")
#             response = model.generate_content(
#                 contents=prompt,
#                 generation_config=genai.types.GenerationConfig(
#                     temperature=temperature
#                 )
#             )

#             content_text = response.candidates[0].content.parts[0].text

#             print("\n--- Token Usage ---")
#             print(f"Prompt Tokens: {response.usage_metadata.prompt_token_count}")
#             print(f"Response Tokens: {response.usage_metadata.candidates_token_count}")
#             print(f"Total Tokens: {response.usage_metadata.total_token_count}\n")

#             return content_text

#         except Exception as e:
#             error_message = str(e)
#             print(f"Attempt {retry_count + 1}: Error generating AI content: {error_message}")

#             if "503" in error_message or "UNAVAILABLE" in error_message.upper():
#                 retry_count += 1
#                 delay = base_delay * (2 ** (retry_count - 1)) + random.uniform(0, 1)
#                 print(f"Retrying in {delay:.2f} seconds...")
#                 time.sleep(delay)
#             else:
#                 break

#     print("Failed to get a valid response after retries.")
#     return None


def extract_json_from_response(response_data):
    match = re.search(r'```json\n(.*?)\n```', response_data, re.DOTALL)
    if match:
        json_str = match.group(1)
        try:
            json_obj = json.loads(json_str)
            return json_obj
        except json.JSONDecodeError as e:
            print("Invalid JSON:", e)
    else:
        print("No JSON block found.")
    return None

def createClaim(response):

    url = "http://18.218.57.115:8090/cc/rest/fnol/v1/createFNOL"

    payload = json.dumps(response)

    headers = {
      'Content-Type': 'application/json',
      'Authorization': 'Basic c3U6Z3c='
    }

    response = requests.request("POST", url, headers=headers, data=payload)

    print(response.text)
    return response

def extract_policy_details(text):
    # Prompt AI to extract the policy number
    prompt = f"""From the following text, extract the policy details in text format. Eg: "PolicyNumber": "12312312". Do not return anything else.\n\n{text}"""
    policy = get_ai_content(prompt)

    # Extract policy number using regex
    match = re.search(r'"PolicyNumber":\s*"(\d+)"', policy)
    if not match:
        print("Policy Number not found.")
        return None

    policy_number = match.group(1)
    print("Extracted Policy Number:", policy_number)

    # Prepare API request
    url = "http://18.218.57.115:8190/pc/rest/policy/v1/latestDetailsBasedOnAccOrPocNo"
    headers = {
        'Content-Type': 'text/plain',
        'Authorization': 'Basic c3U6Z3c='
    }

    payload = f"{policy_number}\r\n"

    # Send request
    try:
        response = requests.post(url, headers=headers, data=payload)
        response.raise_for_status()  # Raises an exception for HTTP 4xx/5xx

        print("Response Received:\n", response.text)
        return response.text,policy_number

    except requests.exceptions.RequestException as e:
        print(f"Error fetching policy details: {e}")
        return None, policy_number


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
