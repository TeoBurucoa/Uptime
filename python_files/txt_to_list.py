def txt_to_list(file_path):
    result = []

    with open(file_path, "r") as file:
        for line in file:
            # Split the line by '|' and strip whitespace from each element
            elements = [elem.strip() for elem in line.split("|")]
            result.append(elements)

    return result

def get_status_info(file_path, status_code):
    code = None
    description = None
    
    try:
        with open(file_path, "r") as file:
            for line in file:
                # Split the line by '|' and strip whitespace
                elements = [elem.strip() for elem in line.split("|")]
                if len(elements) >= 2 and elements[0] == str(status_code):
                    code = elements[0]
                    description = elements[1]
                    break
    
        # If no matching status code was found
        if description is None:
            description = f"The provided status code {status_code} is not mentioned in the {file_path} file"
    
        error_info = f"{code} - {description}"
    except:
        error_info = f"Erreur non identifiable - Error: File {file_path} not found"
    return error_info