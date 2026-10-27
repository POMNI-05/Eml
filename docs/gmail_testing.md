# Test with your own Gmail

A personal `@gmail.com` account works. Complete sign-in in the browser on the
same computer that runs Eml.

## 1. Set up a Google app once

If Google app credentials or authorization are already saved, the opening screen
shows **Connect Gmail** directly and hides the upload form.
Otherwise:

1. Open [Google Cloud Console](https://console.cloud.google.com/) and create or
   choose a project. Enable **Gmail API** in its API Library.
2. Open **Google Auth platform → Branding** and enter an app name and contact
   email.
3. In **Audience**, use **External** for a personal Gmail account. Keep the app
   in **Testing** and add your exact Gmail address under **Test users**.
4. In **Data Access**, add `https://www.googleapis.com/auth/gmail.readonly`.
5. In **Clients**, create a **Desktop app** client and download its JSON file.
6. In Eml's first-time connection panel, upload that JSON and click
   **Save and continue**. The upload form disappears and Gmail sign-in is shown.

Use an OAuth Desktop app JSON, rather than an API key, service account or Google
password. Keep this file on your computer; you do not need to paste it into chat.

## 2. Connect and choose a small test

1. Click **Connect Gmail**, choose your Gmail account in Google's browser page,
   and grant read-only access. Return here and check the connected email address.
2. After connecting, click **Client management**, enter **My Gmail test** and click
   **Add client**, or choose an existing **Client**.
3. Label a few messages **Eml test** in Gmail. In **1. Client & folders**, click
   **Load folders** and select that folder. For the boss's account, choose the
   same client folder paths shown under the Gmail account in Outlook.
4. Choose whether to **Include subfolders** and adjust the date range to when
   those messages were received. The initial limit is 50, adjustable in
   **Period & scope**.
5. Click **Open selected folders →**. The app advances to **Review emails**.
   Read messages beside the checkbox list and keep only 3–5 relevant emails.
   To change a whole sender's emails, choose **Sender**, then **Select sender** or
   **Exclude sender**. **All senders** offers **Select all** and **Exclude all**.
6. Click **Use selected emails →** to continue to the draft.

Folder choices are remembered separately for each client and Gmail account.
You can also choose **Client search** as the email source. In **Find**, type a
name, email address or phrase and press Enter for each entry. Saved client names
and addresses appear as removable entries. With multiple entries, choose **Match ANY
of those written** (either entry may match) or **Match ALL of those written** (every entry must match).
An email address matches the From, To or Cc fields.

**Exclusion filters** offers **Leave out**, **Subject begins with** and **Hide subjects
beginning with**, plus **Leave out from** to choose Anywhere, Sender fields,
To/Cc fields, Subject only or Body only. Each entry is literal text; you do not need to type AND, OR or
minus signs. Subject prefixes ignore case and leading spaces, but include reply
prefixes such as `Re:`. Prefixes are checked on individual messages before the
message limit is counted. **Reset search** restores the client's saved entries
and clears extra filters. Outlook-local and Smart Folders are not Gmail folders.

The app can read mail but cannot send, delete or modify messages. Only the emails
you keep selected enter a new draft's evidence package.

Attachments are extracted automatically for PDF with searchable text, DOCX,
TXT, Markdown, CSV and XLSX. Try an email with a small attachment and expand its
filename in the reading pane to check the text and source location. Unreadable
files and pages are flagged; images and scanned PDFs need OCR text. Excel formulas
are displayed without calculation. Limits: 20 MB per file and 50 MB per fetch.
An attachment is included in AI evidence only while its parent email is included.

## 3. Try a draft

In **3. Draft & export**, open **Draft inputs** to download the **AI evidence package**
without setting up a model. To generate a draft in Eml, open the **Gmail connected**
status pill, then **Local AI setup**,
start Ollama on this computer, click **Load local models**, and choose an
installed model. The [local AI guide](https://github.com/POMNI-05/Eml/blob/main/docs/ollama_setup.md)
has setup details.

Generate the draft, compare activities with their quoted source emails, edit
descriptions and status, then save and export Word or JSON. Ordinary personal
emails may produce no supported professional activity; that is a valid result.

## If sign-in does not work

- **Access denied / app is being tested:** add the account you selected to the
  OAuth project's test users. A personal Gmail account requires External audience.
- **Gmail API disabled:** enable it in the same project as the downloaded JSON.
- **Authorization expired:** use **Gmail connected → Disconnect Gmail**, then connect
  again. Google test-mode authorizations can expire and require a new sign-in.
- **Browser cannot connect back:** run Eml and complete sign-in on the same
  computer. This local app uses a localhost callback.

Official references: [Gmail Python quickstart](https://developers.google.com/workspace/gmail/api/quickstart/python),
[OAuth consent configuration](https://developers.google.com/workspace/guides/configure-oauth-consent),
[Gmail read-only scope](https://developers.google.com/workspace/gmail/api/auth/scopes).
