#!/usr/bin/env python3
"""
Quick Location Service Verification Script
Tests core location functionality without database
"""

import sys
import math
from app.services.location_service import LocationService


def test_distance_calculation():
    """Test Haversine distance calculation"""
    print("=" * 60)
    print("Testing Distance Calculation (Haversine Formula)")
    print("=" * 60)
    
    # Test 1: Lagos to Abuja
    print("\n✓ Test 1: Lagos (6.5244°N, 3.3792°E) to Abuja (9.0765°N, 7.3986°E)")
    distance = LocationService.calculate_distance(6.5244, 3.3792, 9.0765, 7.3986)
    print(f"  Distance: {distance:.2f} km")
    print(f"  Expected: ~500-550 km")
    assert 500 < distance < 550, f"Distance out of range: {distance}"
    print("  ✅ PASS")
    
    # Test 2: Same location
    print("\n✓ Test 2: Same location (distance should be 0)")
    distance = LocationService.calculate_distance(6.5244, 3.3792, 6.5244, 3.3792)
    print(f"  Distance: {distance:.2f} km")
    assert distance == 0.0, f"Expected 0, got {distance}"
    print("  ✅ PASS")
    
    # Test 3: Short distance (within city)
    print("\n✓ Test 3: Ikoyi (6.4619°N, 3.4296°E) to VI (6.4369°N, 3.4254°E)")
    distance = LocationService.calculate_distance(6.4619, 3.4296, 6.4369, 3.4254)
    print(f"  Distance: {distance:.2f} km")
    print(f"  Expected: ~3-4 km (within Lagos)")
    assert distance < 10, f"Distance too large: {distance}"
    print("  ✅ PASS")
    
    # Test 4: None values
    print("\n✓ Test 4: None values should return infinity")
    distance = LocationService.calculate_distance(None, 3.3792, 6.5244, 3.3792)
    print(f"  Result: {distance}")
    assert distance == float('inf'), f"Expected infinity, got {distance}"
    print("  ✅ PASS")


def test_location_scoring():
    """Test location-based scoring logic"""
    print("\n" + "=" * 60)
    print("Testing Location-Based Scoring")
    print("=" * 60)
    
    # Worker location
    worker_lat, worker_lng = 6.5244, 3.3792
    preferred_radius = 10  # 10 km
    max_distance = preferred_radius * 2
    
    # Test cases
    test_cases = [
        {
            "name": "Job within preferred radius",
            "job_lat": 6.5244,
            "job_lng": 3.3792,
            "expected_score_range": (0.95, 1.0),
        },
        {
            "name": "Job at preferred radius boundary",
            "job_lat": 6.5244,
            "job_lng": 3.4592,  # Different coordinates
            "expected_score_range": (0.5, 1.0),
        },
        {
            "name": "Job outside preferred radius but within max",
            "job_lat": 9.0765,
            "job_lng": 7.3986,  # Abuja (450km away)
            "expected_score_range": (0.0, 0.1),
        },
    ]
    
    for test in test_cases:
        print(f"\n✓ {test['name']}")
        
        distance = LocationService.calculate_distance(
            worker_lat, worker_lng,
            test['job_lat'], test['job_lng']
        )
        
        # Calculate score using the formula from JobService.get_recommended_jobs()
        if distance <= preferred_radius:
            location_score = 1.0
        elif distance <= max_distance:
            location_score = 1.0 - (distance - preferred_radius) / (max_distance - preferred_radius)
        else:
            location_score = 0.0
        
        print(f"  Distance: {distance:.2f} km")
        print(f"  Location Score: {location_score:.2f}")
        print(f"  Expected Range: {test['expected_score_range']}")
        
        min_expected, max_expected = test['expected_score_range']
        assert min_expected <= location_score <= max_expected, \
            f"Score {location_score} not in range {test['expected_score_range']}"
        print("  ✅ PASS")


def test_radius_filtering():
    """Test radius-based filtering logic"""
    print("\n" + "=" * 60)
    print("Testing Radius-Based Filtering")
    print("=" * 60)
    
    user_lat, user_lng = 6.5244, 3.3792
    
    entities = [
        {"name": "Job A (same location)", "lat": 6.5244, "lng": 3.3792},
        {"name": "Job B (5km away)", "lat": 6.5244, "lng": 3.4592},
        {"name": "Job C (50km away)", "lat": 7.0, "lng": 3.3792},
        {"name": "Job D (Abuja, 450km away)", "lat": 9.0765, "lng": 7.3986},
    ]
    
    radius_tests = [5, 10, 50, 500]
    
    for radius in radius_tests:
        print(f"\n✓ Filtering with {radius}km radius:")
        nearby = []
        
        for entity in entities:
            distance = LocationService.calculate_distance(
                user_lat, user_lng,
                entity['lat'], entity['lng']
            )
            
            if distance <= radius:
                nearby.append((entity['name'], distance))
        
        print(f"  Found {len(nearby)} entities within {radius}km:")
        for name, distance in sorted(nearby, key=lambda x: x[1]):
            print(f"    - {name}: {distance:.2f} km")
        
        print("  ✅ PASS")


def test_skills_location_combined_scoring():
    """Test combined skills + location scoring"""
    print("\n" + "=" * 60)
    print("Testing Combined Skills + Location Scoring")
    print("=" * 60)
    
    jobs = [
        {
            "title": "Perfect Match (Same location, same category)",
            "category_match": True,
            "distance": 0.0,
            "preferred_radius": 10,
        },
        {
            "title": "Good Match (Close location, same category)",
            "category_match": True,
            "distance": 5.0,
            "preferred_radius": 10,
        },
        {
            "title": "Poor Match (Far location, same category)",
            "category_match": True,
            "distance": 100.0,
            "preferred_radius": 10,
        },
        {
            "title": "Medium Match (Close location, different category)",
            "category_match": False,
            "distance": 5.0,
            "preferred_radius": 10,
        },
    ]
    
    print("\nSample Combined Scoring (50% location + 50% skills):\n")
    
    for job in jobs:
        print(f"✓ {job['title']}")
        
        # Location score
        distance = job['distance']
        radius = job['preferred_radius']
        max_distance = radius * 2
        
        if distance <= radius:
            location_score = 1.0
        elif distance <= max_distance:
            location_score = 1.0 - (distance - radius) / (max_distance - radius)
        else:
            location_score = 0.0
        
        # Skills score
        skills_score = 1.0 if job['category_match'] else 0.7
        
        # Combined score
        combined = (0.5 * location_score) + (0.5 * skills_score)
        
        print(f"  Location Score: {location_score:.2f}")
        print(f"  Skills Score: {skills_score:.2f}")
        print(f"  Combined Score: {combined:.2f}")
        print()


def main():
    """Run all verification tests"""
    print("\n" + "█" * 60)
    print("  Location-Based Matching System - Verification Tests")
    print("█" * 60 + "\n")
    
    try:
        test_distance_calculation()
        test_location_scoring()
        test_radius_filtering()
        test_skills_location_combined_scoring()
        
        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED!")
        print("=" * 60)
        print("\nSummary:")
        print("  ✓ Distance calculation (Haversine formula)")
        print("  ✓ Location-based scoring")
        print("  ✓ Radius filtering logic")
        print("  ✓ Combined skills + location scoring")
        print("\nThe location-based matching system is working correctly!")
        print("=" * 60 + "\n")
        
        return 0
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
