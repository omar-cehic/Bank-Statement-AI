import json
import os
import sys

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

class KeywordCategorizer:
    def __init__(self):
        self.categories = {}
        self.load_categories()

    def load_categories(self):
        """Load categories and keywords from JSON file"""
        try:
            # Get the directory where this script is located
            current_dir = os.path.dirname(__file__)
            categories_file = os.path.join(current_dir, 'categories.json')

            with open(categories_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.categories = data['categories']

            print(f"Loaded {len(self.categories)} categories from categories.json")

        except FileNotFoundError:
            print(f"Warning: categories.json not found at {categories_file}")
            self.categories = {}
        except json.JSONDecodeError as e:
            print(f"Error parsing categories.json: {e}")
            self.categories = {}
        except Exception as e:
            print(f"Error loading categories: {e}")
            self.categories = {}

    def reload_categories(self):
        """Reload categories from JSON file to pick up changes"""
        print("Reloading categories...")
        self.load_categories()

    def categorize_transaction(self, description):
        """
        Categorize a transaction based on its description

        Args:
            description (str): Transaction description/merchant name

        Returns:
            str: Category name or 'Uncategorized' if no match found
        """
        if not description:
            return 'Uncategorized'

        # Convert description to lowercase for case-insensitive matching
        description_lower = description.lower()

        # Check each category's keywords
        for category_name, category_data in self.categories.items():
            keywords = category_data.get('keywords', [])

            # Check if any keyword matches the description
            for keyword in keywords:
                if keyword.lower() in description_lower:
                    return category_name

        # No match found
        return 'Uncategorized'

    def get_category_info(self, category_name):
        """Get description and keywords for a category"""
        if category_name in self.categories:
            return self.categories[category_name]
        return None

    def list_categories(self):
        """List all available categories"""
        return list(self.categories.keys())


def test_categorizer():
    """Test the categorizer with sample merchant names"""
    print("Keyword Categorizer Test")
    print("=" * 50)

    categorizer = KeywordCategorizer()

    # Test cases based on real transaction history
    test_cases = [
        "PANDA EXPRESS #2927 NILES IL",
        "MCDONALD'S F1715 DES PLAINES IL",
        "UNCLE JULIO'S 022 SKOKIE IL",
        "SSA BROOKFIELD ZOO BROOKFIELD IL",  # Should be Uncategorized
        "CLAUDE.AI SUBSCRIPTION ANTHROPIC.COM CA",
        "BP GAS STATION CHICAGO IL",
        "TRADER JOE'S #123 EVANSTON IL",
        "CMX CINEMAS VERNON HILLS IL",
        "LEGO STORE NORTHBROOK IL",
        "WALGREENS #1234 CHICAGO IL",
        "Payment Thank You-Mobile",
        "ALPINE VALLEY SKI RESORT WI",
        "UNKNOWN MERCHANT XYZ"  # Should be Uncategorized
    ]

    print("Testing transaction categorization:")
    print("-" * 50)

    for description in test_cases:
        category = categorizer.categorize_transaction(description)
        print(f"Description: {description}")
        print(f"Category:    {category}")
        print()

    print("Available categories:")
    print("-" * 50)
    for category in categorizer.list_categories():
        info = categorizer.get_category_info(category)
        print(f"• {category}: {info['description']}")

    print("\nTest completed.")


# Allow running this file directly to test categorization
if __name__ == "__main__":
    test_categorizer()