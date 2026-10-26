-- Read-only Legacy Outlook selection. Uses the same dictionary terms as
-- outlook_trigger.applescript, but returns one Internet Message-ID per line.
-- Validate against the installed Outlook version before relying on it.
on extractMessageID(headerText)
    repeat with headerLine in paragraphs of headerText
        set lineText to contents of headerLine
        ignoring case
            if lineText starts with "Message-ID:" then
                set bracketPosition to offset of "<" in lineText
                if bracketPosition > 0 then return text bracketPosition thru -1 of lineText
            end if
        end ignoring
    end repeat
    return missing value
end extractMessageID

tell application "Microsoft Outlook"
    set selectedMessages to selected objects
    if (count of selectedMessages) is 0 then
        error "Please select at least one email." number 1001
    end if
    set messageIDs to {}
    repeat with selectedMessage in selectedMessages
        try
            set emailHeaders to headers of selectedMessage
        on error
            error "A selected object is not a readable email." number 1003
        end try
        set messageID to my extractMessageID(emailHeaders)
        if messageID is missing value then
            error "A selected email has no Internet Message-ID." number 1004
        end if
        if messageID is not in messageIDs then set end of messageIDs to messageID
    end repeat
end tell

set outputText to ""
repeat with messageID in messageIDs
    set outputText to outputText & (contents of messageID) & linefeed
end repeat
return outputText
