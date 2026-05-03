"""Verification script for US-006 migration.

Verifies:
1. Aliases are correctly merged
2. Filtering works as expected
3. Profile loading is correct
"""
from novel_system.graph_name_policy import (
    load_graph_profile,
    resolve_aliases_with_profile,
    normalize_name_with_profile,
    get_effective_seeds_and_aliases,
    is_book_in_whitelist,
    get_policy_mode,
)
from pathlib import Path


def main():
    print("=" * 60)
    print("US-006 Migration Verification")
    print("=" * 60)

    # Load the profile
    profile = load_graph_profile("凡人修仙传")
    print(f"\nBook ID: {profile.book_id}")
    print(f"Seeds count: {len(profile.character_seeds)}")
    print(f"Aliases count: {len(profile.aliases)}")

    # Verify alias merging
    print("\n=== Alias Merging Verification ===")
    test_aliases = ["二愣子", "墨老", "三叔", "韩立三叔"]
    all_aliases_ok = True
    for alias in test_aliases:
        result = resolve_aliases_with_profile(alias, profile)
        expected = {"二愣子": "韩立", "墨老": "墨大夫", "三叔": "韩胖子", "韩立三叔": "韩胖子"}
        ok = result == expected.get(alias, alias)
        status = "OK" if ok else "FAIL"
        print(f"  {alias} -> {result} [{status}]")
        if not ok:
            all_aliases_ok = False

    # Verify filtering
    print("\n=== Filtering Verification ===")
    known_names = profile.character_seeds
    test_names = [
        ("二愣子", "韩立"),  # Should resolve alias
        ("韩立", "韩立"),    # Should stay as-is
        ("张铁", "张铁"),    # Should stay as-is
        ("墨大夫", "墨大夫"), # Should stay as-is
        ("时间", None),      # Should be filtered (generic)
        ("方法", None),      # Should be filtered (generic)
    ]
    all_filtering_ok = True
    for name, expected in test_names:
        result = normalize_name_with_profile(name, known_names, profile)
        ok = result == expected
        status = "OK" if ok else "FAIL"
        print(f"  {name} -> {result} (expected: {expected}) [{status}]")
        if not ok:
            all_filtering_ok = False

    # Verify effective seeds
    seeds, aliases = get_effective_seeds_and_aliases(profile)
    print(f"\nEffective seeds: {len(seeds)}")
    print(f"Effective aliases: {len(aliases)}")

    # Verify all aliases point to valid seeds
    print("\n=== Alias Validity Check ===")
    all_valid = True
    for alias, canonical in profile.aliases.items():
        if canonical not in profile.character_seeds:
            print(f"  WARNING: Alias {alias} -> {canonical} but {canonical} not in seeds")
            all_valid = False
        else:
            print(f"  OK: {alias} -> {canonical}")

    # Verify whitelist
    print("\n=== Whitelist Verification ===")
    in_whitelist = is_book_in_whitelist("凡人修仙传")
    mode = get_policy_mode("凡人修仙传")
    print(f"  is_book_in_whitelist('凡人修仙传'): {in_whitelist}")
    print(f"  get_policy_mode('凡人修仙传'): {mode}")
    whitelist_ok = in_whitelist is True and mode == "profile"

    # Summary
    print("\n" + "=" * 60)
    print("VERIFICATION SUMMARY")
    print("=" * 60)
    print(f"  Alias merging: {'PASS' if all_aliases_ok else 'FAIL'}")
    print(f"  Filtering: {'PASS' if all_filtering_ok else 'FAIL'}")
    print(f"  Alias validity: {'PASS' if all_valid else 'FAIL'}")
    print(f"  Whitelist: {'PASS' if whitelist_ok else 'FAIL'}")

    all_passed = all_aliases_ok and all_filtering_ok and all_valid and whitelist_ok
    print(f"\n  OVERALL: {'ALL CHECKS PASSED' if all_passed else 'SOME CHECKS FAILED'}")
    print("=" * 60)

    return 0 if all_passed else 1


if __name__ == "__main__":
    exit(main())
