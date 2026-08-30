import ast
from ..access import LilyDatabaseAccess
from typing import Dict

class BloxFruitsDatabase(LilyDatabaseAccess):
    def __init__(self):
        super().__init__()
        self.item_dict: dict[str, dict] = {}
        self._cache_ready = False

    
    async def load_cache(self):
        rows = await self.fetch_all("SELECT * FROM BF_ItemValues")

        self.item_dict.clear()

        for row in rows:
            (
                name,
                physical_value,
                permanent_value,
                physical_demand,
                permanent_demand,
                demand_type,
                permanent_demand_type,
                category,
                aliases,
                icon_url,
                rarity
            ) = row

            if not name:
                continue

            name_lower = name.lower()

            try:
                aliases = ast.literal_eval(aliases) if aliases else []
                if not isinstance(aliases, list):
                    aliases = []
            except (ValueError, SyntaxError):
                aliases = []

            self.item_dict[name_lower] = {
                "name": name,
                "physical_value": physical_value or 0,
                "permanent_value": permanent_value or 0,
                "physical_demand": physical_demand or "",
                "permanent_demand": permanent_demand or "",
                "demand_type": demand_type or "",
                "permanent_demand_type": permanent_demand_type or "",
                "category": (category or "").lower(),
                "aliases": aliases,
                "icon_url": icon_url,
                "name_lower": name_lower,
                "rarity": rarity
            }

        self._cache_ready = True

    @property   
    def alias_map(self):
        return {
            alias.lower(): name
            for name, data in self.item_dict.items()
            for alias in data.get("aliases", [])
            if alias
        }
    
    @property
    def fruit_names(self):
        return set(self.item_dict.keys())
    
    @property
    def fruit_names_sorted(self):
        return sorted(self.item_dict.keys(), key=len, reverse=True)
    
    @property
    def item_list_minimal(self):
        return [
            {
                "name": data["name"],
                "name_lower": data["name_lower"],
                "category": data["category"],
                "physical_value": data["physical_value"],
                "permanent_value": data["permanent_value"]
            }
            for data in self.item_dict.values()
        ]
    
    @property
    def item_category(self) -> Dict[str, int]:
        return {
        'common': 1,
        'uncommon': 2,
        'rare': 3,
        'legendary': 4,
        'mythical': 5,
        'gamepass': 6
    }

    def get_category(self, item_name: str) -> str | None:
        if isinstance(item_name, str):
            fruit_name = ' '.join(i if i[0].isdigit() else i.capitalize() for i in item_name.split())
            data = self.item_dict.get(fruit_name.lower(), {}) or self.item_dict.get(fruit_name.title(), {})
            return data["category"]
        else:
            return None

    def fetch_fruit_details(self, fruit_name: str) -> dict:
        if isinstance(fruit_name, str):
            fruit_name = ' '.join(i if i[0].isdigit() else i.capitalize() for i in fruit_name.split())
            data = self.item_dict.get(fruit_name.lower(), {}) or self.item_dict.get(fruit_name.title(), {})

            return data
        else:
            return {}

    def get_item_value(self, item_name: str, item_type: str) -> int:
        if isinstance(item_name, str):
            fruit_name = ' '.join(i if i[0].isdigit() else i.capitalize() for i in item_name.split())
            data = self.item_dict.get(fruit_name.lower(), {}) or self.item_dict.get(fruit_name.title(), {})
            if item_type.lower() == "physical":
                return data["physical_value"]
            else:
                return data["permanent_value"]
        else:
            return 0