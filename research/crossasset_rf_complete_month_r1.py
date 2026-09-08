from __future__ import annotations

import sys

import combined_cross_sectional_ml_full_pass_r1 as base
import combined_cross_sectional_ml_full_pass_r1_complete_month as guarded

base.CHILDREN["crossasset_rf"] = ("crossasset", "rf")
base._feature_panel = guarded._complete_month_feature_panel

if __name__ == "__main__":
    sys.argv.extend([])
    base.main()
