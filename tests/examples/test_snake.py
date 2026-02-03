from __future__ import annotations

import importlib.util
import random
from pathlib import Path


def _load_snake_module() -> object:
    """
    Load the snake example module from the examples directory.
    """
    path = Path("examples/snake/main.py")
    spec = importlib.util.spec_from_file_location("snake_example", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load snake example module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


snake = _load_snake_module()


def test_place_food_avoids_snake() -> None:
    """
    Ensure food placement does not overlap with snake body.
    """
    rng = random.Random(0)
    snake_cells = [(0, 0), (1, 0), (2, 0)]
    food = snake._place_food(rng, 4, 2, snake_cells)
    assert food not in snake_cells


def test_step_game_moves_and_eats() -> None:
    """
    Ensure movement and eating update state correctly.
    """
    state = snake.SnakeState(5, 5, [(2, 2), (1, 2)], (1, 0), (3, 2))
    event = snake._step_game(state)
    assert event == "eat"
    assert state.score == 1
    assert state.snake[0] == (3, 2)
    assert len(state.snake) == 3

    state.food = (4, 4)
    event = snake._step_game(state)
    assert event == "move"
    assert state.snake[0] == (4, 2)
    assert len(state.snake) == 3


def test_step_game_hits_wall() -> None:
    """
    Ensure hitting walls ends the game.
    """
    state = snake.SnakeState(3, 3, [(2, 1), (1, 1)], (1, 0), (0, 0))
    event = snake._step_game(state)
    assert event == "dead"
    assert state.alive is False


def test_update_direction_ignores_reverse() -> None:
    """
    Ensure direct reversal is ignored for safety.
    """
    current = (1, 0)
    requested = (-1, 0)
    updated = snake._update_direction(current, requested)
    assert updated == current


def test_sanitize_nickname_uppercases_and_trims() -> None:
    """
    Ensure nicknames keep only letters and max length three.
    """
    assert snake._sanitize_nickname("ab1") == "AB"
    assert snake._sanitize_nickname("aBcd") == "ABC"
