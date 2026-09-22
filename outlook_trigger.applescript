on extractMessageID(headerText)

	set headerLines to paragraphs of headerText

	repeat with headerLine in headerLines

		set lineText to contents of headerLine

		ignoring case
			if lineText starts with "Message-ID:" then

				set bracketPosition to offset of "<" in lineText

				if bracketPosition > 0 then
					return text bracketPosition thru -1 of lineText
				end if

			end if
		end ignoring

	end repeat

	return missing value

end extractMessageID


-- Bring Outlook to the front first
tell application "Microsoft Outlook"
	activate
end tell

delay 0.5


tell application "Microsoft Outlook"

	set selectedObjects to selected objects

	-- MVP: require exactly one selected object
	if (count of selectedObjects) is 0 then
		error "Please select an email first." number 1001
	end if

	if (count of selectedObjects) > 1 then
		error "Please select only one email." number 1002
	end if

	set selectedMessage to item 1 of selectedObjects

	-- Make sure it behaves like a message
	try
		set emailSubject to subject of selectedMessage
	on error
		error "The selected Outlook object is not an email message." number 1003
	end try

	-- Sender
	set senderObject to sender of selectedMessage
	set senderName to name of senderObject
	set senderEmail to address of senderObject

	-- Date
	set emailDate to time received of selectedMessage

	-- Folder is optional
	set folderName to ""

	try
		set outlookFolder to folder of selectedMessage

		if outlookFolder is not missing value then
			set folderName to name of outlookFolder
		end if
	on error
		set folderName to ""
	end try

	-- Message-ID
	set emailHeaders to headers of selectedMessage
	set messageID to my extractMessageID(emailHeaders)

end tell


if messageID is missing value then
	error "Could not find Internet Message-ID." number 1004
end if


-- Machine-readable separator
set fieldSeparator to ASCII character 31

set outputText to ¬
	messageID & fieldSeparator & ¬
	emailSubject & fieldSeparator & ¬
	senderName & fieldSeparator & ¬
	senderEmail & fieldSeparator & ¬
	(emailDate as text) & fieldSeparator & ¬
	folderName

return outputText


-- Debug only:
(*
set displayText to ¬
	"Message-ID: " & messageID & return & ¬
	"Subject: " & emailSubject & return & ¬
	"Sender name: " & senderName & return & ¬
	"Sender email: " & senderEmail & return & ¬
	"Received: " & (emailDate as text) & return & ¬
	"Folder: " & folderName

display dialog displayText
*)