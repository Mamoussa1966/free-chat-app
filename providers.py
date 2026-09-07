if seat.kind == "openai_responses":
    content = [{"type": "input_text", "text": prompt}]

    for attachment in attachments:
        if attachment.get("omitted"):
            name = attachment.get(
                "name",
                "attachment",
            )

            content.append(
                {
                    "type": "input_text",
                    "text": (
                        "Attached file omitted from inline API "
                        "payload because it exceeds the provider "
                        "payload safety cap: "
                        f"{name}"
                    ),
                }
            )
        else:
            content.append(
                {
                    "type": "input_file",
                    "filename": attachment.get(
                        "name",
                        "attachment",
                    ),
                    "file_data": as_base64(
                        attachment
                    ),
                }
            )
