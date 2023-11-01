import urllib.parse, aiohttp, string, random

BASE_CHARS = string.ascii_lowercase + string.ascii_uppercase + string.digits

def find_by_key(key, match, collection : list, *, match_lowercase = False):
    if match_lowercase: parsed_match = match.lower()
    else: parsed_match = match
    for i in collection:
        attr_val = getattr(i, key)
        if match_lowercase: attr_val = attr_val.lower()
        if attr_val == parsed_match: return i

def url_encode(data : str) -> str: return urllib.parse.quote(data)

async def http_request(method : str, url : str, data = None, headers = None):
    async with aiohttp.ClientSession() as s:
        async with s.request(method, url, data=data, headers=headers) as response:
            return await response.text()

def generate_string(str_len : int):
    return ''.join(random.choices(BASE_CHARS, k=str_len))

def strip_string(text : str, valids : str):
    out = ''
    for i in text:
        if i in valids:
            out += i
    return out

def unique_string(text : str, taken : list[str], case_insensitive = True):
    if case_insensitive:
        parsed_taken = [i.lower() for i in taken]
        parsed_text = text.lower()
    else:
        parsed_taken = taken
        parsed_text = text

    if not parsed_text in parsed_taken: return text
    suffix = 1
    while (parsed_text + str(suffix)) in parsed_taken:
        suffix += 1
    return text + str(suffix)

def linked_string(string_items : list[str], primary_separator : str, last_separator : str):
    if len(string_items) == 0: return ''
    if len(string_items) == 1: return string_items[0]
    return primary_separator.join(string_items[:-1]) + last_separator + string_items[-1]