import streamlit as st
import pandas as pd
import openai 
import os
import zipfile
import boto3
from io import BytesIO
from docx import Document

from dotenv import load_dotenv
load_dotenv()

GPT_MODEL = 'gpt-4'

openai.api_key = os.getenv("OPENAI_API_KEY")

aws_access_key_id = st.secrets["aws"]["aws_access_key_id"]
aws_secret_access_key = st.secrets["aws"]["aws_secret_access_key"]
aws_default_region = st.secrets["aws"]["aws_default_region"]

system_prompt = """

    Your task is to serve as an assistant bot generating personalized thank you notes to donors of the non-profit organization, Meals On Wheels San Diego County, based on data given.

    The bot should include the donor's address, city, state, zip code on the very top as shown in the sample conversation.
    The bot should be slightly creative, yet must maintain consistency, tone, and length of the sample conversations.
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


def generate_letter(row, date, sname, spos, semail, sphone, snote):

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

        TODAYS DATE: {date}
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

        SENDER NAME: {sname}
        SENDER POSITION: {spos}
        SENDER EMAIL: {semail}
        SENDER PHONE NUMBER: {sphone}

        SPECIAL NOTES: {snote}

    """
    
    output = get_chat_response(prompt)

    print(output)

    return output


def main():

    st.subheader("MOW-GPT — LLM Donor Communication Tool")

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

        progress.empty()  # Clear the progress bar
        st.success("Document successfully uploaded to S3!")
        st.write(f"[Download the document]({url})")

if __name__ == "__main__":
    main()