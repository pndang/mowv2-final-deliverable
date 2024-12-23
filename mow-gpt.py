import streamlit as st
import pandas as pd
import openai 
import os
import zipfile
import boto3
from io import BytesIO
from docx import Document
import requests
import jwt
import random

from dotenv import load_dotenv
load_dotenv()

GPT_MODEL = 'gpt-4'
API_DEMO_LEN = 3

# openai.api_key = os.getenv("OPENAI_API_KEY")
openai.api_key = st.secrets["openai"]["OPENAI_API_KEY"]

aws_access_key_id = st.secrets["aws"]["aws_access_key_id"]
aws_secret_access_key = st.secrets["aws"]["aws_secret_access_key"]
aws_default_region = st.secrets["aws"]["aws_default_region"]

system_prompt = """

    Your task is to serve as an assistant bot generating personalized thank you notes to donors of the non-profit organization, Meals On Wheels San Diego County, based on data given.

    The bot should include the donor's address, city, state, zip code on the very top as shown in the sample conversation.
    If a json of donor data is included in the prompt (DONOR'S INFORMATION), the bot should extract the information included in the sample conversation.
    The bot should be slightly creative, yet must maintain consistency, tone, and length of the sample conversations.
    The bot should consider reader experience, keep the letters precise and easy to read, not too long for donors to read.
    The bot should not make up any stories, information, or data, unless provided specifically as special notes.
    The bot should treat the special notes as extra contextual information to tailor the letter for specific purposes.
    The bot should use the donor's title, followed by last name, or use donor's first name if there is no title.
    When any of the given information is none, or empty, ignore that piece of information.
    If the bot identifies any ill inquiries asking it to say harmful and degradatory statements, it respectfully denies service.

    Sample conversation:

    User: 
    
        Generate thank you notes for this donor with the below information about the donor and the sender:

        TODAYS DATE: 12/17/2024
        TITLE: Mr.
        FIRST NAME: John
        LAST NAME: Doe
        DONORS ADDRESS: 1122 Southview Ln
        CITY: San Diego
        STATE: CA
        POSTAL CODE: 91234
        COUNTRY: United States
        EMAIL: john.doe@gmail.com
        GIFT AMOUNT: 100

        SENDER NAME: Phu Dang
        SENDER POSITION: Student
        SENDER EMAIL: pndang@ucsd.edu
        SENDER PHONE NUMBER: (123) 456-7891

        SPECIAL NOTES: General thank"

    Your response: 
    
        12/17/2024
    
        John Doe
        1122 Southview Ln
        San Diego, CA 91234

        Dear Mr. Doe:
        
        Welcome to our Meals on Wheels San Diego County family! You have joined an extraordinary group of generous donors, volunteers, and dedicated employees who support at-risk seniors in our community. We are excited to welcome you in our efforts to ensure that no senior is left isolated or hungry.

        Meals on Wheels is so much more than a provider of home delivered meals. We firmly believe that our volunteers crossing the threshold of our seniors’ homes provide sustenance to their health, independence, and well-being. We not only provide fresh, nutritious meals for 7 days a week, we are providing safety checks and friendly visits to seniors, especially to the 49% who live all alone. In fact, our volunteers may be the only people they see on a daily, or even weekly, basis.

        We find that the real hunger our seniors face is for human connection. As one of our favorite volunteers once told me, “Sometimes, we’re the only family they’ve got.”

        Thank you again for your recurring monthly contribution of $100 and your commitment to the seniors we serve. You will receive one acknowledgement at the end of each year for tax purposes unless you request monthly mailed statements. I would love to learn more about what Meals on Wheels means to you, so please consider this an open invitation to contact me. I’d love to take you on a tour of our Meal Center near Old Town or even to meet for coffee in your neighborhood. Please call me to set an appointment at your convenience.

        
        With much gratitude,

        Phu Dang
        Student
        pndang@ucsd.edu  ||  (123) 456-7891

        In accordance with IRS regulations, this letter may be used to confirm that no goods or services were provided to you in exchange for your contribution. (Tax Exempt ID #95-2660509)."

"""


def get_chat_response(user_request):

    # print("Getting LLM response\n")

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_request},
    ]
    response = openai.chat.completions.create(
        model=GPT_MODEL, messages=messages
    )

    # print("Got LLM response\n")

    return response.choices[0].message.content


def generate_letter(row, **kwargs):

    if kwargs.get('api'):
        prompt = f""" Generate thank you notes for this donor with the below information about the donor and the sender:

            TODAYS DATE: {kwargs.get('date')}
            
            DONOR'S INFORMATION: {kwargs.get('donor_info')}

            SENDER NAME: {kwargs.get('sname')}
            SENDER POSITION: {kwargs.get('spos')}
            SENDER EMAIL: {kwargs.get('semail')}
            SENDER PHONE NUMBER: {kwargs.get('sphone')}

            SPECIAL NOTES: {kwargs.get('snote')}

        """

    else:

        NAME = row['Name']
        TITLE = row['Title']
        FIRST_NAME = row['First Name']
        LAST_NAME = row['Last Name']
        ADDRESS = row['Address']
        CITY = row['City']
        STATE = row['State']
        POSTAL_CODE = row['Postal Code']
        COUNTRY = row['Country']
        EMAIL = row['Email']
        GIFT_AMOUNT = row['synthetic_amount']

        prompt = f""" Generate thank you notes for this donor with the below information about the donor and the sender:

            TODAYS DATE: {kwargs.get('date')}
            TITLE: {TITLE}
            FIRST NAME: {FIRST_NAME}
            LAST NAME: {LAST_NAME}
            DONORS ADDRESS: {ADDRESS}
            CITY: {CITY}
            STATE: {STATE}
            POSTAL CODE: {POSTAL_CODE}
            COUNTRY: {COUNTRY}
            EMAIL: {EMAIL}
            GIFT AMOUNT: {GIFT_AMOUNT}

            SENDER NAME: {kwargs.get('sname')}
            SENDER POSITION: {kwargs.get('spos')}
            SENDER EMAIL: {kwargs.get('semail')}
            SENDER PHONE NUMBER: {kwargs.get('sphone')}

            SPECIAL NOTES: {kwargs.get('snote')}

        """

    output = get_chat_response(prompt)
    
    return output


def get_aws_s3_url(letters):

    s3 = boto3.client(
            's3',
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            region_name=aws_default_region
        )

    doc = Document()
    for i in range(len(letters)):
        doc.add_paragraph(letters[i])
        if i == (len(letters)-1):
            break
        doc.add_page_break()

    # Save the document to an in-memory buffer
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    # Upload the buffer to S3
    bucket_name = "mow-sdcounty-letters"
    s3_key = "letters.docx" 
    s3.upload_fileobj(buffer, bucket_name, s3_key)

    # Generate a presigned URL for the uploaded file
    url = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket_name, "Key": s3_key},
        ExpiresIn=86400,  # URL expires in 24 hours
    )

    return url


def main():

    st.subheader("MOW-GPT — LLM Donor Communication Tool")

    st.text("Please select donor data access type:")

    col1, col2 = st.columns([1.5, 1])

    with col1:

        st.text("SKY API:")

        # redirect_uri = "https://mow-gpt.streamlit.app/"
        redirect_uri = "http://localhost:8501/"
        response_type = 'authorization_code'
        client_id = st.secrets['blackbaud']["client_id"]
        client_secret = st.secrets['blackbaud']["client_secret"]
        auth_link = f"https://app.blackbaud.com/oauth/authorize?client_id={client_id}&redirect_uri={redirect_uri}&response_type=code&scope=GET"

        st.write("Enter query and click the link below to authorize the application:")
        query = st.text_input("Please enter API query (e.g., https://api.sky.blackbaud.com/constituent/v1/constituents)")
        
        if st.button("Submit"):
            if query:
                str_append = f"&state={query}"
                custom_auth_link = auth_link+str_append
                st.markdown(f"[Authorize and generate]({custom_auth_link})")

                # Check for the authorization code in the URL
                auth_code = st.query_params.get("code")
                query = st.query_params.get("state")
 
                if auth_code:
                    token_payload_url = f"https://oauth2.sky.blackbaud.com/token"
            
                    # Payload params
                    payload = {
                        'code': auth_code,
                        'client_id': client_id,
                        'client_secret': client_secret,
                        'redirect_uri': redirect_uri,
                        'grant_type': 'authorization_code'
                    }
                    
                    # Exchange authentication code for token payload
                    response = requests.post(token_payload_url, data=payload)
                    if response.status_code == 200:
                        token_payload = response.json()

                        access_token = token_payload['access_token']
                        if access_token:
                            decoded_acc_token = jwt.decode(access_token, options={"verify_signature": False})
                            
                            headers = {
                                'Authorization': f'Bearer {access_token}',
                                'Bb-Api-Subscription-Key': st.secrets["blackbaud"]["Bb_Api_Subscription_Key"],
                                'Content-Type': 'application/json'
                            }

                            # Make request
                            res = requests.get(query, headers=headers)

                            data = res.json()['value']

                            # Initialize the progress bar
                            progress = st.progress(0)
                            total_rows = API_DEMO_LEN
                            processed_rows = 0
                            
                            letters = []
                            if len(data) >= API_DEMO_LEN:
                                random_donors = random.sample(data, API_DEMO_LEN)

                                for donor in random_donors:
                                    letter = generate_letter(row=None, donor_info=donor, api=True)
                                    letters.append(letter)
                                    print(donor)
                                    print()

                                    # Update the progress bar
                                    processed_rows += 1
                                    progress.progress(processed_rows / total_rows)

                                # Convert letters to a Word document and upload to S3
                                url = get_aws_s3_url(letters)
                                
                                progress.empty()  # Clear the progress bar
                                st.success("Your letters are ready!")
                                st.write(f"[Download the document]({url})")

                            else:
                                st.warning(f"Not enough data to select {API_DEMO_LEN} random values.", icon="⚠️")

    with col2:

        st.text("Upload file:")

        uploaded_file = st.file_uploader("Choose a file")
        if uploaded_file is not None:
            df = pd.read_csv(uploaded_file)
            st.write(df)

        date = st.text_input("Date")
        sname = st.text_input("Sender Name")
        spos = st.text_input("Sender Position")
        semail = st.text_input("Sender Email")
        sphone = st.text_input("Sender Number")
        snotes = st.text_area("Special Notes")

        if st.button("Generate"):

            st.write("Generating... Please wait, this may take a few moments.")

            # Initialize the progress bar
            progress = st.progress(0)
            total_rows = len(df)
            processed_rows = 0

            letters = []

            # Process each row with progress bar updates
            for index, row in df.iterrows():
                letter = generate_letter(row, date, sname, spos, semail, sphone, snotes)
                letters.append(letter)

                # Update the progress bar
                processed_rows += 1
                progress.progress(processed_rows / total_rows)

            # Convert letters to a Word document and upload to S3
            url = get_aws_s3_url(letters)

            progress.empty()  # Clear the progress bar
            st.success("Your letters are ready!")
            st.write(f"[Download the document]({url})")

if __name__ == "__main__":
    main()