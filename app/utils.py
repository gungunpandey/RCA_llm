import re

def clean_part(part):
    part = part.strip()
    if not part:
        return ""
    # Remove leading titles: Mr., Mr, Mrs., Mrs, Dr., Dr, Ms., Ms, Mr, Mrs, etc.
    part = re.sub(r"^(?:mr|mrs|ms|dr|md)\.?\s*", "", part, flags=re.IGNORECASE)
    part = part.strip()
    # Normalize internal spaces
    part = re.sub(r"\s+", " ", part)
    # Remove trailing dot if it's not a single letter abbreviation (like V.)
    if part.endswith(".") and not (len(part) >= 3 and part[-3] == ' ' and part[-2].isalpha()):
        part = part[:-1].strip()
    return part

def normalize_name(name):
    cleaned = clean_part(name)
    cleaned_lower = cleaned.lower()
    
    # Mapping rules (case-insensitive keys)
    mapping = {
        "debasis jena": "Debasish Jena",
        "debashis jena": "Debasish Jena",
        "debasish jena": "Debasish Jena",
        "d jena": "Debasish Jena",
        "d. jena": "Debasish Jena",
        
        "s k muduli": "S. K. Muduli",
        "s.k. muduli": "S. K. Muduli",
        "s. k. muduli": "S. K. Muduli",
        "s.k.muduli": "S. K. Muduli",
        "sk muduli": "S. K. Muduli",
        
        "nitish kumar": "Nitish Kumar",
        "nitisih kumar": "Nitish Kumar",
        "nitesh kumar": "Nitish Kumar",
        
        "siddhartha mahapatra": "Siddhartha Mahapatra",
        "sidharth mohapatra": "Siddhartha Mahapatra",
        "sidharta mahapatra": "Siddhartha Mahapatra",
        "siddharth mahapatra": "Siddhartha Mahapatra",
        
        "manish kumar singh": "Manish Kumar Singh",
        "manish singh": "Manish Kumar Singh",
        
        "raghu": "Raghu V.",
        "raghu v": "Raghu V.",
        "raghu v.": "Raghu V.",
        "raghu viswanadhu": "Raghu V.",
        
        "bhajahari das": "Bhajahari Das",
        "anurag ray": "Anurag Ray",
        
        "kaushal singh": "Kaushal Kishor Singh",
        "kaushal kishor singh": "Kaushal Kishor Singh",
        "kausal singh": "Kaushal Kishor Singh",
        "kausal kishor singh": "Kaushal Kishor Singh",
        
        "bijay pradhan": "Bijay Pradhan",
        "bijayasen pradhan": "Bijay Pradhan",
        
        "uday singh": "Uday Kumar Singh",
        "uday kumar singh": "Uday Kumar Singh",
        
        "ashis sahu": "Ashis Kumar Sahu",
        "ashis kumar sahu": "Ashis Kumar Sahu",
        "ashish sahoo": "Ashis Kumar Sahu",
        "ashish sahu": "Ashis Kumar Sahu",
        "ashis sahoo": "Ashis Kumar Sahu",
        
        "chitta ranjan sahoo": "Chitta Ranjan Sahoo",
        "o p singh": "Om Prakash Singh",
        "om prakash singh": "Om Prakash Singh",
        "sourav mohanty": "Sourav Mohanty",
        "ganesh mohanty": "Ganesh Mohanty",
        "b s chandel": "B. S. Chandel",
        "jiten patra": "Jiten Patra",
        "ashish mishra": "Ashish Mishra",
        "kumar maharana": "Kumar Maharana",
        "sunil das": "Sunil Das",
        "akash mohanty": "Akash Mohanty"
    }
    
    if cleaned_lower in mapping:
        return mapping[cleaned_lower]
        
    # Default fallback: Title Case if it's a general name
    if cleaned_lower and cleaned_lower not in ["-", "unknown", "unassigned"]:
        if "shift-in" in cleaned_lower or "team" in cleaned_lower or "dept" in cleaned_lower:
            return cleaned
        return cleaned.title()
    return cleaned or "Unassigned"

def normalize_full_owner_string(owner_str):
    if not owner_str or owner_str.strip() in ("", "-", "Unassigned"):
        return "Unassigned"
        
    # Split by any of the separators: newlines, &, +, commas, and the word "and"
    parts = re.split(r"(?i)[\n+&,]|\band\b", owner_str)
    
    unique_names = []
    seen = set()
    for part in parts:
        if part is None:
            continue
            
        # Check for newline separator in split parts
        if "\n" in part:
            continue
            
        stripped = part.strip()
        if stripped in ["&", "+", ",", "and"]:
            continue
        elif stripped:
            norm = normalize_name(stripped)
            if norm and norm != "Unassigned" and norm.lower() not in seen:
                unique_names.append(norm)
                seen.add(norm.lower())
                
    if not unique_names:
        return "Unassigned"
    return " & ".join(unique_names)

def clean_equipment_name(name: str) -> str:
    if not name:
        return ""
    name = name.lower().strip()
    # Replace common abbreviations
    name = re.sub(r'\bpbm\b', 'primary ball mill', name)
    name = re.sub(r'\bfp\b', 'filter press', name)
    name = re.sub(r'\bw\.?f\.?\b', 'weigh feeder', name)
    
    # Strip non-alphanumeric characters
    name = re.sub(r'[^a-z0-9]', '', name)
    # Strip trailing digits
    name = re.sub(r'\d+$', '', name)
    return name

