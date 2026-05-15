#!/usr/bin/env python3
"""
Test script to verify storyboard display fix - should show multiple scenes
"""
import requests
import json
import sys

BASE_URL = "http://localhost:5000"

# Test cases with different story lengths
test_cases = [
    {
        "name": "Short story (2 sentences)",
        "text": "女孩看着天空。泪水滑落。",
    },
    {
        "name": "Medium story (4 sentences)",
        "text": "早上阳光洒满房间。她起床，打开窗户。看到街道下面的人群。心想今天又是新的一天。",
    },
    {
        "name": "Long story (6+ sentences)",
        "text": "他独自走在城市的街道上。路人匆匆而过，没有人注意他。他抬头看着高楼大厦。突然下起了大雨。他找到一个地方躲雨。望着雨幕，思绪万千。",
    },
]

def test_storyboard():
    print("\n" + "="*60)
    print("Testing Storyboard Display Fix")
    print("="*60)
    
    for test in test_cases:
        print(f"\n📖 Testing: {test['name']}")
        print(f"Story: {test['text']}")
        print("-" * 60)
        
        payload = {
            "text": test['text'],
            "use_ai": False  # Use rule-based for quick test
        }
        
        try:
            response = requests.post(
                f"{BASE_URL}/api/storyboard",
                json=payload,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                sequence = data.get("sequence", [])
                
                scene_count = len(sequence)
                print(f"✅ Scenes generated: {scene_count}")
                
                if scene_count == 0:
                    print("❌ ERROR: No scenes generated!")
                else:
                    for i, scene in enumerate(sequence, 1):
                        segment = scene.get("segment", "")[:20]
                        emoji = scene.get("emoji", "")
                        print(f"   Scene {i}: {emoji} - {segment}...")
                    
                    # Verify minimum scene count
                    sentence_count = len([s for s in test['text'].split('。') if s.strip()])
                    if sentence_count <= 3:
                        min_expected = 3
                    elif sentence_count <= 6:
                        min_expected = 4
                    else:
                        min_expected = 5
                    
                    if scene_count >= min_expected:
                        print(f"✅ Scene count meets requirement (>= {min_expected})")
                    else:
                        print(f"⚠️  WARNING: Scene count {scene_count} < min {min_expected}")
            else:
                print(f"❌ API Error: {response.status_code}")
                print(response.text)
                
        except Exception as e:
            print(f"❌ Request failed: {e}")

if __name__ == "__main__":
    print("Note: Make sure Flask server is running on localhost:5000")
    test_storyboard()
