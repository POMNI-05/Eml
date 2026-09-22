from pprint import pprint
# pprint is a nice way to print nested data structures in a readable way. 
# we use pprint here because Email metadata is a dictionary, and it contains other dictionaries and lists inside it.
#   pprint will format it nicely for us to read.

from outlook_adapter import get_selected_outlook_email, OutlookSelectionError
# get_selected_outlook_email retrieves the metadata of the selected email in Outlook.

email = get_selected_outlook_email()

pprint(email)