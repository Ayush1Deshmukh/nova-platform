import json
import os
import sys

def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    rules_path = os.path.join(base_dir, "config", "customer_rules.json")
    
    if not os.path.exists(rules_path):
        print(f"Warning: Rules file not found at {rules_path}")
        print("Please ensure the configuration exists before validating.")
        return

    try:
        with open(rules_path, 'r') as f:
            rules = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error parsing rules JSON: {e}")
        sys.exit(1)

    print("=== Customer Rules Validation ===")
    
    # Assuming standard structure of rules (adjust as necessary)
    if not isinstance(rules, dict):
        print("Invalid structure: Expected top-level JSON dictionary.")
        sys.exit(1)
        
    print(f"Loaded rules for {len(rules.keys())} customer(s).")
    
    for customer, customer_rules in rules.items():
        print(f"\nCustomer: {customer}")
        
        # Validation rules
        doc_rules = customer_rules.get("document_rules", {})
        print("  Document Rules:")
        if not doc_rules:
            print("    None defined.")
        for doc_type, type_rules in doc_rules.items():
            print(f"    - {doc_type}: {len(type_rules)} rules found.")
            
        # Cross document rules
        cross_doc_rules = customer_rules.get("cross_document_rules", [])
        print("  Cross-Document Rules:")
        if not cross_doc_rules:
            print("    None defined.")
        for i, rule in enumerate(cross_doc_rules, 1):
            print(f"    {i}. {rule.get('description', 'Unnamed rule')}")

    print("\nValidation complete. Rules structure is valid.")

if __name__ == "__main__":
    main()
