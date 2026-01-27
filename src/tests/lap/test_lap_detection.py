"""圈數偵測測試腳本。

測試三個樣本檔案的圈數偵測結果。

使用方法：
    python -m src.tests.lap.test_lap_detection
"""

from ...rehab_analyzer import RehabilitationSessionAnalyzer


def main() -> None:
    files = [
        ("data/npy/1_1_1031.npy", "中風患者"),
        ("data/npy/4_1_1208.npy", "正常人"),
        # ("data/npy/1_1_607.npy", "正常人"),
    ]

    for path, label in files:
        print(f"=== {path} ({label}) ===")
        analyzer = RehabilitationSessionAnalyzer(path)
        
        det = analyzer.detect_laps_auto()
        print(f"Laps: {det.num_laps}")
        print(f"Chair pos: ({det.chair_pos[0]:.2f}, {det.chair_pos[1]:.2f})")
        print(f"Cone pos: ({det.cone_pos[0]:.2f}, {det.cone_pos[1]:.2f})")
        print(f"Chair radius: enter={det.r_chair_enter:.2f}m, exit={det.r_chair_exit:.2f}m")
        print(f"Cone radius: enter={det.r_cone_enter:.2f}m, exit={det.r_cone_exit:.2f}m")
        print(f"FPS: {det.fps:.1f}")
        
        for i, lap in enumerate(det.laps):
            print(f"\n  Lap {i+1}:")
            print(f"    Time: {lap.ts_start:.1f}s ~ {lap.ts_end:.1f}s (total: {lap.dur_total:.1f}s)")
            print(f"    Direction: {lap.lap_direction}")
            print(f"    Phases:")
            print(f"      Stand up: {lap.dur_stand:.2f}s")
            print(f"      Walk to cone: {lap.dur_to_cone:.2f}s")
            print(f"      Cone turn: {lap.dur_cone_turn:.2f}s")
            print(f"      Return: {lap.dur_return:.2f}s")
            print(f"      Turn to sit: {lap.dur_turn_to_sit:.2f}s")
            print(f"      Sit down: {lap.dur_sit:.2f}s")
            print(f"    Distances:")
            print(f"      Outbound: {lap.dist_outbound_m:.2f}m")
            print(f"      Return: {lap.dist_return_m:.2f}m")
            print(f"      Total path: {lap.dist_lap_path_m:.2f}m")
            print(f"      Chair-Cone: {lap.dist_chair_cone_centers_m:.2f}m")
            print(f"    Turns:")
            print(f"      Cone: {lap.delta_theta_cone_deg:.1f}° (dir={lap.turn_cone_dir})")
            print(f"      Chair: {lap.delta_theta_chair_deg:.1f}° (dir={lap.turn_chair_dir})")


if __name__ == "__main__":
    main()
