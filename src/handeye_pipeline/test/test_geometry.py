import numpy as np

from handeye_pipeline.geometry import (
    compose_transform,
    invert_transform,
    matrix_to_transform,
    transform_to_matrix,
)


def test_transform_round_trip():
    transform = {
        "translation": [0.1, -0.2, 0.3],
        "rotation": [0.0, 0.0, 0.3826834324, 0.9238795325],
    }
    matrix = transform_to_matrix(transform)
    round_trip = matrix_to_transform(matrix)
    assert np.allclose(round_trip["translation"], transform["translation"])
    assert np.allclose(abs(np.dot(round_trip["rotation"], transform["rotation"])), 1.0)


def test_compose_inverse_is_identity():
    transform = {
        "translation": [0.1, 0.2, 0.3],
        "rotation": [0.0, 0.0, 0.0, 1.0],
    }
    identity = compose_transform(transform, invert_transform(transform))
    assert np.allclose(identity["translation"], [0.0, 0.0, 0.0])
    assert np.allclose(identity["rotation"], [0.0, 0.0, 0.0, 1.0])
