tell application "Microsoft Outlook"
	activate
end tell

delay 0.5

tell application "Microsoft Outlook"

	set selectedObjects to selected objects

	if (count of selectedObjects) is 0 then
		error "Please select an email first." number 1001
	end if

	set selectedMessage to item 1 of selectedObjects

	try
		set emailSubject to subject of selectedMessage
	on error
		error "The selected Outlook object is not an email message." number 1002
	end try

end tell

return emailSubject