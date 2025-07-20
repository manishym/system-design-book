#!/usr/bin/env python3
"""
Demonstration of Special Character Handling in Consistent Hashing KV Store

This script shows how to use the new POST endpoints for handling keys 
with special characters that would cause issues in URL paths.
"""

import requests
import sys
import os

# Add the parent directory to Python path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from storage.kvstore.kvstore_service import KVStoreClient


def demo_special_characters():
    """Demonstrate handling of keys with special characters"""
    
    print("🔍 Special Character Handling Demo")
    print("=" * 50)
    
    # Example special keys that would cause URL issues
    special_keys = [
        "key/with/slashes",
        "key with spaces", 
        "key@with#symbols$%",
        "key:with:colons",
        "key?with&query=params",
        "key[with]brackets",
        "key{with}braces",
        "特殊字符键",  # Unicode characters
        "clé_spéciale",  # Accented characters
        "🔑_emoji_key"  # Emoji in key
    ]
    
    print("\n📦 Keys with Special Characters:")
    for i, key in enumerate(special_keys, 1):
        print(f"  {i:2d}. '{key}'")
    
    # Direct KV Store API Examples
    print("\n🚀 Direct API Usage Examples:")
    print("-" * 30)
    
    kvstore_url = "http://localhost:8080"  # Assuming KV store is running
    
    for key in special_keys[:3]:  # Test first 3 keys
        value = f"value_for_{key.replace(' ', '_').replace('/', '_')}"
        
        print(f"\n📝 Testing key: '{key}'")
        
        # Store using PUT (always uses POST body)
        print("  1. Storing value...")
        try:
            response = requests.post(
                f"{kvstore_url}/put",
                json={"key": key, "value": value},
                timeout=5
            )
            if response.status_code == 200:
                print(f"     ✅ Stored successfully")
            else:
                print(f"     ❌ Store failed: {response.status_code}")
                continue
        except Exception as e:
            print(f"     ❌ Store error: {e}")
            continue
        
        # Retrieve using POST method (handles special chars)
        print("  2. Retrieving with POST method...")
        try:
            response = requests.post(
                f"{kvstore_url}/get",
                json={"key": key},
                timeout=5
            )
            if response.status_code == 200:
                data = response.json()
                print(f"     ✅ Retrieved: '{data['value']}'")
            else:
                print(f"     ❌ Retrieve failed: {response.status_code}")
        except Exception as e:
            print(f"     ❌ Retrieve error: {e}")
        
        # Try old GET method (will fail for special chars)
        print("  3. Comparing with GET method...")
        try:
            response = requests.get(f"{kvstore_url}/get/{key}", timeout=5)
            if response.status_code == 200:
                print(f"     ✅ GET method also works")
            else:
                print(f"     ⚠️  GET method failed: {response.status_code} (expected for special chars)")
        except Exception as e:
            print(f"     ⚠️  GET method error: {e} (expected for special chars)")
        
        # Delete using POST method
        print("  4. Deleting with POST method...")
        try:
            response = requests.post(
                f"{kvstore_url}/delete",
                json={"key": key},
                timeout=5
            )
            if response.status_code == 200:
                print(f"     ✅ Deleted successfully")
            else:
                print(f"     ❌ Delete failed: {response.status_code}")
        except Exception as e:
            print(f"     ❌ Delete error: {e}")
    
    print("\n🧠 Client Library Usage:")
    print("-" * 25)
    
    # Using the enhanced KVStoreClient (automatically handles special chars)
    try:
        client = KVStoreClient("localhost:8000")  # Gateway address
        
        test_key = "special/key@with#symbols"
        test_value = "This value has a special key!"
        
        print(f"\n📝 Using client library with key: '{test_key}'")
        
        # Store
        print("  1. Storing...")
        success = client.put(test_key, test_value)
        if success:
            print("     ✅ Stored using client library")
        else:
            print("     ❌ Store failed")
            
        # Retrieve
        print("  2. Retrieving...")
        retrieved = client.get(test_key)
        if retrieved == test_value:
            print(f"     ✅ Retrieved: '{retrieved}'")
        else:
            print(f"     ❌ Retrieved unexpected: '{retrieved}'")
            
        # Delete
        print("  3. Deleting...")
        success = client.delete(test_key)
        if success:
            print("     ✅ Deleted using client library")
        else:
            print("     ❌ Delete failed")
            
    except Exception as e:
        print(f"  ⚠️  Client library demo skipped: {e}")
        print("     (Gateway might not be running)")
    
    print("\n📋 Summary:")
    print("-" * 10)
    print("✅ POST /put         - Always works (key in body)")
    print("✅ POST /get         - Works with special chars (key in body)")
    print("✅ GET /get/<key>    - Works with simple keys only")
    print("✅ POST /delete      - Works with special chars (key in body)")
    print("✅ DELETE /delete/<key> - Works with simple keys only")
    print("\n💡 Use POST methods for keys with special characters!")
    print("💡 Client library automatically chooses the right method!")


def test_url_encoding_issues():
    """Show the URL encoding issues with GET methods"""
    
    print("\n🔍 URL Encoding Issues Demo")
    print("=" * 35)
    
    problematic_keys = [
        ("key with spaces", "key%20with%20spaces"),
        ("key/with/slashes", "key%2Fwith%2Fslashes"), 
        ("key@symbol", "key%40symbol"),
        ("key#hash", "key%23hash"),
        ("key?query=param", "key%3Fquery%3Dparam")
    ]
    
    for original, encoded in problematic_keys:
        print(f"\nKey: '{original}'")
        print(f"  URL encoded: '{encoded}'")
        print(f"  GET /get/{original} ← Will likely fail")
        print(f"  GET /get/{encoded} ← Might work but ugly")
        print(f"  POST /get + body    ← Always works! ✅")


if __name__ == "__main__":
    print("🚀 Starting Special Character Handling Demo")
    print("📋 Make sure a KV store is running on localhost:8080")
    print("📋 Optionally, have a gateway running on localhost:8000")
    print()
    
    try:
        demo_special_characters()
        test_url_encoding_issues()
        
        print("\n✅ Demo completed successfully!")
        print("💡 The new POST endpoints solve URL encoding issues for special characters.")
        
    except KeyboardInterrupt:
        print("\n⏹️  Demo interrupted by user")
    except Exception as e:
        print(f"\n❌ Demo failed: {e}")
        sys.exit(1) 