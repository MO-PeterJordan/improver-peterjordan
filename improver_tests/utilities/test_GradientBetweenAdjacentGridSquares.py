# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# (C) British Crown copyright. The Met Office.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# * Redistributions of source code must retain the above copyright notice, this
#   list of conditions and the following disclaimer.
#
# * Redistributions in binary form must reproduce the above copyright notice,
#   this list of conditions and the following disclaimer in the documentation
#   and/or other materials provided with the distribution.
#
# * Neither the name of the copyright holder nor the names of its
#   contributors may be used to endorse or promote products derived from
#   this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
""" Tests of GradientBetweenAdjacentGridSquares plugin."""

import numpy as np
import pytest
from iris.cube import Cube
from iris.coords import DimCoord
from iris.coord_systems import CoordSystem

from improver.metadata.constants.attributes import MANDATORY_ATTRIBUTE_DEFAULTS
from improver.synthetic_data.set_up_test_cubes import set_up_variable_cube
from improver.utilities.spatial import GradientBetweenAdjacentGridSquares


EXAMPLE_INPUT_DATA_1 = np.array([[0, 1, 2], [3, 4, 5], [4, 5, 6]], dtype=np.float32)

EXAMPLE_INPUT_DATA_2 = np.array(
    [[0, 1, 2], [1095014, 0, -1095014], [4, 5, 6]], dtype=np.float32
)

EXAMPLE_INPUT_DATA_3 = np.array(
    [[1000, 2000, 1000], [40, 50, 60], [400, 500, 600]], dtype=np.float32
)

EXAMPLE_INPUT_DATA_4 = np.array(
    [[-40, 5, 50], [-50, 10000, 60], [-25, 4, 40]], dtype=np.float32
)


EQUAL_AREA_GRID_SPACING = 1000  # Metres
LATITUDE_GRID_SPACING = 10  # Degrees
LONGITUDE_GRID_SPACING = 10  # Degrees
# Distances covered when travelling 10 degrees north-south or east-west:
X_GRID_SPACING_AT_EQUATOR = 1111949  # Metres
X_GRID_SPACING_AT_10_DEGREES_NORTH = 1095014  # Metres
X_GRID_SPACING_AT_20_DEGREES_NORTH = 1044735  # Metres
Y_GRID_SPACING = 1111949  # Metres


def regrid_x_with_wrap_around_interpolation_for_edge_points(data):
    first_col = data[:, [0]]
    second_col = data[:, [1]]
    third_col = data[:, [2]]
    regridded_first_col = (first_col + third_col) / 2
    regridded_second_col = (first_col + second_col) / 2
    regridded_third_col = (second_col + third_col) / 2
    return np.hstack((regridded_first_col, regridded_second_col, regridded_third_col))


def regrid_x_with_extrapolation_for_edge_points(data):
    x_diff = np.diff(data, axis=1)
    first_col = data[:, [0]]
    second_col = data[:, [1]]
    regridded_first_col = first_col - x_diff / 2
    regridded_second_col = (first_col + second_col) / 2
    regridded_third_col = second_col + x_diff / 2
    return np.hstack((regridded_first_col, regridded_second_col, regridded_third_col))


def regrid_x(data: np.ndarray, wrap_around_meridian) -> np.ndarray:
    """
    Regrids an array using linear interpolation/extrapolation.
    If wrap_around_meridian is false, function expects a  3 x 2 array which it regrids to a
    3 x 3 array using linear interpolation/extrapolation.
    If wrap_around_meridian is true, expects a 3 x 3 array, which is regridded to another 3 x 3
    array using linear interpolaton only, with the first column of the output array interpolated
    between the first and last columns of the input array.
    """
    if wrap_around_meridian:
        return regrid_x_with_wrap_around_interpolation_for_edge_points(data)
    else:
        return regrid_x_with_extrapolation_for_edge_points(data)


def regrid_y(data: np.ndarray) -> np.ndarray:
    """
    Regrids a 2 x 3 array to a 3 x 3 array using linear interpolation/extrapolation.
    """
    y_diff = np.diff(data, axis=0)
    first_row = data[0]
    second_row = data[1]
    regridded_first_row = first_row - y_diff / 2
    regridded_second_row = (first_row + second_row) / 2
    regridded_third_row = second_row + y_diff / 2
    return np.vstack((regridded_first_row, regridded_second_row, regridded_third_row))


def get_expected_gradients(
    param_array, x_separations, y_separations, regrid=False, wrap_around_meridian=False
):
    """
    Calculates the gradient of a 2d numpy array along the x and y axes, accounting for distance
    between the points.
    Gradients are calculated between grid points, meaning that the resulting arrays will be smaller
    by one dimension along the axis of differentiation.
    """
    x_diff = np.diff(param_array, axis=1)
    x_grad = x_diff / x_separations
    y_diff = np.diff(param_array, axis=0)
    y_grad = y_diff / y_separations
    if regrid:
        x_grad = regrid_x(x_grad, wrap_around_meridian)
        y_grad = regrid_y(y_grad)
    return x_grad, y_grad


#  Todo: the below is a copypasta from test_DistanceBetweenGridPoints. Need to make the code shared instead.
#  Options:
#       - Make the one in test_Distance slightly more generic (take either data or shape) and copy from there.
#       - Make the one in test_Distance take data only and have the tests themselves hand in the np.ones.
#       - Extract the function to a common test utils place... this is probably the correct approach, but it means I'm competing with the existing helper, which doesn't work for me because I need different x and y coords.
#       - Amend the existing one to meet my needs (and update everything this breaks :'(   )
def make_test_cube(
        data: np.ndarray,
        coordinate_system: CoordSystem,
        x_axis_name: str,
        x_axis_values: np.ndarray,
        y_axis_name: str,
        y_axis_values: np.ndarray,
        xy_axis_units: str,
) -> Cube:
    """Creates an example cube for use as test input."""

    dimcoords = [
            (
                DimCoord(
                    y_axis_values,
                    standard_name=y_axis_name,
                    units=xy_axis_units,
                    coord_system=coordinate_system,
                ),
                0,
            ),
            (
                DimCoord(
                    x_axis_values,
                    standard_name=x_axis_name,
                    units=xy_axis_units,
                    coord_system=coordinate_system,
                ),
                1,
            ),
        ]
        cube = Cube(
            example_data,
            standard_name="land_ice_basal_temperature",
            units="kelvin",
            dim_coords_and_dims=dimcoords,
        )
        return cube



@pytest.fixture(name="make_expected")
def make_expected_fixture() -> callable:
    """Factory as fixture for generating a cube of varying size."""

    def _make_expected(values, spatial_grid_type, grid_spacing) -> Cube:
        """Create a cube filled with data of a specific shape and value."""
        data = np.array(values, dtype=np.float32)
        cube = set_up_variable_cube(
            data,
            name="gradient_of_wind_speed",
            units="s^-1",
            spatial_grid=spatial_grid_type,
            grid_spacing=grid_spacing,
            attributes=MANDATORY_ATTRIBUTE_DEFAULTS,
            domain_corner=(0.0, 0.0),
        )
        return cube

    return _make_expected


@pytest.fixture(name="make_input")
def make_wind_speed_fixture() -> callable:
    """Factory as fixture for generating a wind speed cube as test input."""

    def _make_input(data, spatial_grid, latitude_grid_spacing, longitude_grid_spacing, wrap_around_meridian=False) -> Cube:
        """Wind speed in m/s"""

        cube = Cube(data, name="wind_speed", units="m s^-1", dim_coords_and_dims=)
        #     set_up_variable_cube(
        #     data,
        #     name="wind_speed",
        #     units="m s^-1",
        #     spatial_grid=spatial_grid,
        #     grid_spacing=grid_spacing,
        #     domain_corner=(0.0, 0.0),
        # )
        if wrap_around_meridian:
            cube.coord(axis="x").circular = True
        return cube

    return _make_input


@pytest.mark.parametrize(
    "grid",
    (
        {"regrid": False, "xshape": (3, 2), "yshape": (2, 3)},
        {"regrid": True, "xshape": (3, 3), "yshape": (3, 3)},
    ),
)
@pytest.mark.parametrize(
    "input_data",
    [
        EXAMPLE_INPUT_DATA_1,
        EXAMPLE_INPUT_DATA_2,
        EXAMPLE_INPUT_DATA_3,
        EXAMPLE_INPUT_DATA_4,
    ],
)
def test_gradient_equal_area_coords(make_input, make_expected, grid, input_data):
    """
    Check calculating the gradient with and without regridding for equal area coordinate systems
    """
    x_distances = np.full(
        (input_data.shape[0], input_data.shape[1] - 1), EQUAL_AREA_GRID_SPACING
    )
    y_distances = np.full(
        (input_data.shape[0] - 1, input_data.shape[1]), EQUAL_AREA_GRID_SPACING
    )
    expected_x_gradients, expected_y_gradients = get_expected_gradients(
        input_data, x_distances, y_distances, regrid=grid["regrid"]
    )
    wind_speed = make_input(
        input_data, "equalarea", EQUAL_AREA_GRID_SPACING
    )
    expected_x = make_expected(
        expected_x_gradients, "equalarea", EQUAL_AREA_GRID_SPACING
    )
    expected_y = make_expected(
        expected_y_gradients, "equalarea", EQUAL_AREA_GRID_SPACING
    )
    gradient_x, gradient_y = GradientBetweenAdjacentGridSquares(regrid=grid["regrid"])(
        wind_speed
    )
    for result, expected in zip((gradient_x, gradient_y), (expected_x, expected_y)):
        assert result.name() == expected.name()
        assert result.attributes == expected.attributes
        assert result.units == expected.units
        np.testing.assert_allclose(expected.data, result.data, rtol=1e-5, atol=1e-4)


@pytest.mark.parametrize(
    "grid",
    (
        {"regrid": False, "xshape": (3, 2), "yshape": (2, 3)},
        {"regrid": True, "xshape": (3, 3), "yshape": (3, 3)},
    ),
)
@pytest.mark.parametrize(
    "input_data",
    [
        EXAMPLE_INPUT_DATA_1,
        EXAMPLE_INPUT_DATA_2,
        EXAMPLE_INPUT_DATA_3,
        EXAMPLE_INPUT_DATA_4,
    ],
)
@pytest.mark.parametrize("wrap_around_meridian", [True, False])
def test_gradient_lat_lon_coords(make_input, make_expected, grid, input_data, wrap_around_meridian):
    """
    Check calculating the gradient with and without regridding
    for global latitude/longitude coordinate system
    """
    wind_speed = make_input(input_data, "latlon", LATITUDE_GRID_SPACING, LONGITUDE_GRID_SPACING, wrap_around_meridian)
    x_separations = np.array(
        [
            [X_GRID_SPACING_AT_EQUATOR, X_GRID_SPACING_AT_EQUATOR],
            [X_GRID_SPACING_AT_10_DEGREES_NORTH, X_GRID_SPACING_AT_10_DEGREES_NORTH],
            [X_GRID_SPACING_AT_20_DEGREES_NORTH, X_GRID_SPACING_AT_20_DEGREES_NORTH],
        ]
    )
    y_separations = np.full(
        (input_data.shape[0] - 1, input_data.shape[1]), Y_GRID_SPACING
    )
    expected_x_gradients, expected_y_gradients = get_expected_gradients(
        input_data, x_separations, y_separations, grid["regrid"], wrap_around_meridian
    )

    expected_x = make_expected(expected_x_gradients, "latlon", LATLON_GRID_SPACING)
    expected_y = make_expected(expected_y_gradients, "latlon", LATLON_GRID_SPACING)
    gradient_x, gradient_y = GradientBetweenAdjacentGridSquares(regrid=grid["regrid"])(
        wind_speed
    )
    for result, expected in zip((gradient_x, gradient_y), (expected_x, expected_y)):
        assert result.name() == expected.name()
        assert result.attributes == expected.attributes
        assert result.units == expected.units
        np.testing.assert_allclose(expected.data, result.data, rtol=2e-3, atol=1e-5)
