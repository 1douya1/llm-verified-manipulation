from handeye_pipeline.config import load_config


def test_default_config_loads():
    config = load_config("src/handeye_pipeline/config/uf850_realsense_eye_to_hand.yaml")
    assert config.calibration.mode == "eye_to_hand"
    assert config.robot.base_frame == "link_base"
    assert config.camera.optical_frame == "camera_color_optical_frame"
    assert config.board.squares_x == 5
