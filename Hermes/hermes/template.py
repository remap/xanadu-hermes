from __future__ import annotations
import json
import re
from pathlib import Path
from typing import Any

class Template:
    """
    Example usage:
        # Suppose 'sample_data.json' contains:
        # { "name": "Alice", "city": "Wonderland", "weather": "sunny" }

        tpl = Template("sample_data.json")
        output = tpl.replace("Hello {{name}}, welcome to {{city}}! It's a {{weather}} day.")
        print(output)  # "Hello Alice, welcome to Wonderland! It's a sunny day."
    """

    def __init__(self, mapping: dict[str, Any]) -> None:
        self.mapping = mapping

    @classmethod
    def from_json_file(cls, json_file: str | Path) -> Template:
        path = Path(json_file)
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return cls(data)

    @classmethod
    def from_json_string(cls, json_string: str) -> Template:
        data = json.loads(json_string)
        return cls(data)

    def replace(self, text: str) -> str:
        pattern = re.compile(r"{{(.*?)}}")
        def replacer(match: re.Match) -> str:
            key = match.group(1).strip()
            return str(self.mapping.get(key, f"{{{{{key}}}}}"))
        return pattern.sub(replacer, text)

    def dump_mapping(self) -> str:
        # Customize how you want it displayed:
        # Below uses "key: value" pairs, one per line.
        lines = [f"{k}: {v}" for k, v in self.mapping.items()]
        return "\n".join(lines)

    def add(self, key: str, value: Any) -> None:
        """
        Add or update a single key-value pair in the mapping.

        :param key: The placeholder key you want to insert or update.
        :param value: The value associated with 'key'.
        """
        self.mapping[key] = value

    def add_dict (self, new_data: dict[str, Any]) -> None:
        """
        Add or update multiple key-value pairs from a dictionary in the mapping.

        :param new_data: Dictionary of key-value pairs to add or update.
        """
        self.mapping.update(new_data)

    def remove(self, key: str) -> bool:
        """
        Remove a single key-value pair from the mapping if it exists.

        :param key: The placeholder key to remove.
        :return: True if the key was present and removed, False otherwise.
        """
        return self.mapping.pop(key, None) is not None

    def replace_in_dict(self, data: Any) -> Any:
        """
        Recursively replace string values in nested dictionaries (and lists)
        using the current mapping.

        :param data: A dict, list, string, or any other type that might
                     contain strings with {{placeholders}}.
        :return: A copy of the data structure with replaced string values.
        """
        if isinstance(data, dict):
            # Create a new dict with replaced/recursively transformed values
            return {k: self.replace_in_dict(v) for k, v in data.items()}
        elif isinstance(data, list):
            # Process each element of the list
            return [self.replace_in_dict(item) for item in data]
        elif isinstance(data, str):
            # Perform template replacement on a plain string
            return self.replace(data)
        else:
            # Other types (int, float, None, etc.) - no change
            return data

if __name__ == "__main__":
    # sample_file = "sample_data.json"
    # test_string = (
    #     "Hello {{name}}, welcome to {{city}}!\n"
    #     "It's a {{weather}} day, isn't it, {{name}}?"
    # )
    # tpl = Template.from_json_file(sample_file)
    # result = tpl.replace(test_string)
    # print("Original text:\n", test_string)
    # print("\nReplaced text:\n", result)

    json_string_data = '{"name": "Bob",   "world" : "/Game/_Sets/Fall_24/ML_Xanadu_JB.ML_Xanadu_JB"}'
    tpl_str = Template.from_json_string(json_string_data)
    text_str = "A JSON string says: Hello {{name}} from {{world}}!"
    print("Original text:", text_str)
    print("Replaced  text:", tpl_str.replace(text_str))
    print(tpl_str.dump_mapping())