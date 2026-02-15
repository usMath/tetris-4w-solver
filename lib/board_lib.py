from collections import deque
import os.path
import pickle
import random
from typing import Dict, Generator, List, Set, Tuple, TypeAlias, Callable

### UTILITY FUNCTIONS ###

# Rotations, used for debugging
ROTATIONS = ["N", "E", "S", "W"]
ROTATION_MOVES = ["0", "CW", "180", "CCW"]

# File names
PIECES_FILENAME = os.path.dirname(__file__) + "/../data/pieces.txt"
KICKS_FILENAME = os.path.dirname(__file__) + "/../data/kicks.txt"
CORNERS_FILENAME = os.path.dirname(__file__) + "/../data/corners.txt"
PC_QUEUES_FILENAME = os.path.dirname(__file__) + "/../data/pc-queues.txt"

# Types
Piece: TypeAlias = str
Queue: TypeAlias = str
Coordinate: TypeAlias = Tuple[int, int]
CoordinateList: TypeAlias = List[Coordinate]
CoordinateSet: TypeAlias = Set[Coordinate]
Board: TypeAlias = List[List[int]]
BoardHash: TypeAlias = int
IndexState: TypeAlias = Tuple[int, BoardHash, Piece]
Finesse: TypeAlias = int
PieceFinesse: TypeAlias = Tuple[Finesse]

def get_pieces_from_file(filename: str) -> Dict[Piece, Dict[int, CoordinateList]]:
  """Reads piece data from a text file.

  Returns a dictionary: `{piece: {orientation: [minos relative to center]}}`.
  Coordinates are stored as `(y, x)`.
  Center of piece should always be on the second line second character.
  """
  pieces = {}
  with open(filename, 'r') as input_file:
    piece_list = input_file.readline().strip()
    for piece in piece_list:
      pieces[piece] = {}
      minos = []
      row1 = input_file.readline().strip()
      row0 = input_file.readline().strip()
      for i in range(4):
        if row0[i] != ".":
          minos.append((0, i-1))
        if row1[i] != ".":
          minos.append((1, i-1))
      for rotation in range(4):
        pieces[piece][rotation] = tuple(minos)
        minos = [(-x, y) for (y, x) in minos]
  return pieces

def get_piece_widths(pieces: Dict[Piece, Dict[int, CoordinateList]]) -> Dict[Piece, int]:
  piece_widths = {}
  for piece in pieces:
    left = min(pieces[piece][0], key=lambda k:k[1])[1]
    right = max(pieces[piece][0], key=lambda k:k[1])[1]
    piece_widths[piece] = right - left + 1
  return piece_widths

PIECES = get_pieces_from_file(PIECES_FILENAME)
PIECE_WIDTHS = get_piece_widths(PIECES)
# Null piece
NULL_PIECE = "?"

def get_kicks_from_file(filename: str) -> Dict[Piece, Dict[int, Dict[int, CoordinateList]]]:
  """Reads kick data from a text file.

  Returns a dictionary: `{piece: {orientation: {input: [offset order]}}}`
  """
  kicks = {}
  with open(filename, 'r') as input_file:
    for _p in range(7):
      piece = input_file.readline().strip()
      kicks[piece] = {}
      for orientation in range(4):
        kicks[piece][orientation] = {}
        for rotation_input in range(1, 4):
          input_file.readline()
          offsets = input_file.readline().strip().split("; ")
          piece_kicks = [tuple(map(int, _.split(", "))) for _ in offsets]
          kicks[piece][orientation][rotation_input] = piece_kicks
  return kicks

KICKS = get_kicks_from_file(KICKS_FILENAME)

def get_corners_from_file(filename: str) -> Dict[Piece, List[CoordinateList]]:
  """Reads corner data from a text file.

  Returns a dictionary: `{piece: [list of corner_list]}`
  """
  corners = {}
  with open(filename, 'r') as input_file:
    num_pieces = int(input_file.readline())
    for piece_num in range(num_pieces):
      piece = input_file.readline().strip()
      corners[piece] = []
      for rotation_num in range(4):
        offsets = input_file.readline().strip().split("; ")
        orientation_corner_list = [tuple(map(int, _.split(", "))) for _ in offsets]
        corners[piece].append(orientation_corner_list)
  return corners

CORNERS = get_corners_from_file(CORNERS_FILENAME)

# Finesse values
FINESSE_L = 0
FINESSE_R = 1
FINESSE_CW = 2
FINESSE_CCW = 3
FINESSE_180 = 4
FINESSE_SD = 5
FINESSE_HOLD = 6

NULL_FINESSE: PieceFinesse = ()

FINESSE_TRANSFORM = {
    FINESSE_L : "moveLeft",
    FINESSE_R : "moveRight",
    FINESSE_CW : "rotateCW",
    FINESSE_CCW : "rotateCCW",
    FINESSE_180 : "rotate180",
    FINESSE_SD : "softDrop",
    FINESSE_HOLD : "hold"
  }
def transform_finesse(piece_finesse: Finesse) -> str:
  """Converts a piece finesse to a string for bot output."""
  return FINESSE_TRANSFORM[piece_finesse]

def hash_board(board: Board) -> BoardHash:
  """Converts a board state to an integer.

  Treats board state like binary string. Bits are read top to bottom, and right to left within each row.
  """
  board_hash = 0
  for row in reversed(board):
    for square in reversed(row):
      board_hash *= 2
      board_hash += square
  return board_hash

def unhash_board(board_hash: BoardHash) -> Board:
  """Converts an integer to a board state.

  Treats board state like binary string. Bits are read top to bottom, and right to left within each row.
  """
  board = []
  while board_hash > 0:
    row_hash = board_hash % 16
    board_hash //= 16
    board.append([])
    for square_num in range(4):
      board[-1].append(row_hash % 2)
      row_hash //= 2
  return board

EMPTY_BOARD_HASH: BoardHash = 0  # Board hash of empty board

def num_minos(board_hash: BoardHash) -> int:
  """Computes number of minos in the board state corresponding to a hash."""
  minos = 0
  while board_hash > 0:
    minos += board_hash % 2
    board_hash //= 2
  return minos

def get_mino_list(board: Board) -> CoordinateList:
  """Obtains list of minos in the board."""
  mino_list = []
  for y in range(len(board)):
    for x in range(4):
      if board[y][x]:
        mino_list.append((y, x))
  return mino_list

def lines_to_insert(board_height: int, max_lines: int) -> Generator[Tuple[int, ...], None, None]:
  """Obtains list of ways to insert at most `max_lines` lines into a board."""
  if max_lines == 1:
    yield ()
    for height in range(board_height+1):
      yield (height,)
  else:
    for line_set in lines_to_insert(board_height, max_lines - 1):
      yield (*line_set, board_height)
    if board_height > 0:
      for line_set in lines_to_insert(board_height - 1, max_lines):
        yield line_set
    else:
      yield ()

def generate_7bag() -> Generator[Piece, None, None]:
    """Generates an infinite number of 7bag pieces."""
    pieces = list(PIECES.keys())
    index = len(pieces)
    while True:
      if index == len(pieces):
        random.shuffle(pieces)
        index = 0
      yield pieces[index]
      index += 1

def all_queues(queue_length: int) -> Generator[Queue, None, None]:
  """Generates all queues (ignoring bag structure) of length `queue_length`"""
  if queue_length <= 0:
    yield ""
  else:
    for piece in PIECES:
      for queue in all_queues(queue_length-1):
        yield queue + piece

def get_queue_orders(queue: Queue) -> Generator[Queue, None, None]:
  """Obtains all possible ways to play a queue given one hold."""
  if len(queue) == 1:
    yield queue[0]
    return
  for queue_order in get_queue_orders(queue[1:]):
    yield queue[0] + queue_order
  for queue_order in get_queue_orders(queue[0] + queue[2:]):
    yield queue[1] + queue_order

def is_piece_location_valid(mino_set: CoordinateSet, mino_offsets: CoordinateList, piece_y: int, piece_x: int):
  """Determines if a piece location is in board bounds and does not intersect board."""
  for (offset_y, offset_x) in mino_offsets:
    y = piece_y + offset_y
    x = piece_x + offset_x
    if (y, x) in mino_set or y < 0 or x < 0 or x >= 4:
      return False
  return True

def is_piece_location_spin(mino_set: CoordinateSet, piece: Piece, rotation: int, piece_y: int, piece_x: int):
  """Determines if a piece location and rotation counts as a spin under 3 corner handheld rule.

  Assumes initial location is valid.
  Assumes previous action is a rotation.
  """
  if piece not in CORNERS:
    return False
  corner_count = 0
  for corner_num in range(4):
    corner_x = piece_x + CORNERS[piece][rotation][corner_num][0]
    corner_y = piece_y - CORNERS[piece][rotation][corner_num][1]
    if (
      corner_y < 0
      or not 0 <= corner_x < 4
      or (corner_y, corner_x) in mino_set
    ):
      corner_count += 1
  return corner_count >= 3

def get_gravity_y(mino_set: CoordinateSet, mino_offsets: CoordinateList, start_y: int, start_x: int):
  """Compute vertical position of piece after sonic drop.
  
  Assumes initial location is valid.
  """
  current_y = start_y - 1
  floor_y = -min([offset[0] for offset in mino_offsets])
  while current_y >= floor_y:
    is_floating = True
    for (offset_y, offset_x) in mino_offsets:
      if (current_y + offset_y, start_x + offset_x) in mino_set:
        is_floating = False
        break
    if not is_floating:
      break
    current_y -= 1
  current_y += 1
  return current_y

def get_finesse_number(finesse_list: List[PieceFinesse]):
  """Returns total number of keypresses to execute the finesse of the queue specified by the list."""
  return sum(len(piece_finesse) for piece_finesse in finesse_list)

def display_board(board_hash: BoardHash) -> None:
  """Displays a board."""
  board = unhash_board(board_hash)
  print("|    |")
  for row in reversed(board):
    print(f"|{''.join([[' ', '#'][_] for _ in row])}|")
  print("+----+")

def display_boards(board_hash_list: List[BoardHash]) -> None:
  """Displays a list of boards."""
  for board_hash in board_hash_list:
    display_board(board_hash)
    print()

def score_num_minos(mino_count: int) -> int:
  """Return mino score of a board with given mino count of `mino_count`.

  This is used for an additional tiebreak on assessing board quality.
  This is based on distance from 6, 9, 12, or 15 minos.
  This also strongly dislikes a mino count of 4.
  """
  if mino_count == 4:
    return 400
  target = [12, 9, 6, 15][mino_count % 4]
  return abs(mino_count - target)

def get_input_queues_for_output_sequence(target: Queue, hold: Piece) -> Generator[Queue, None, None]:
  """Obtains queues that with the given hold could place the specified pieces."""
  if len(target) == 0:
    yield ""
  elif target[0] == hold:
    for piece in PIECES:
      for queue in get_input_queues_for_output_sequence(target[1:], piece):
        yield piece + queue
  else:
    for queue in get_input_queues_for_output_sequence(target[1:], hold):
      yield target[0] + queue

### MAIN FUNCTIONS AND STRUCTURES ###

# Results of get_next_boards
TRANSITION_CACHE = {}
# Board hash of board with equivalent finesse
SIMPLIFICATION_CACHE = {}

def get_next_boards(
    board_hash: BoardHash,
    piece: Piece,
    no_breaks: bool = False,
    can_180: bool = True
  ) -> Dict[BoardHash, Tuple[bool, PieceFinesse]]:
  """Computes and caches all possible piece placements given board and piece.

  Returns a dictionary of all possible boards, with whether a spin was performed an their finesse.

  `board_hash` is the hash of the input board.

  `piece` is the next piece.

  If `no_breaks` is True, then only returns placements that do not break combo.

  If `can_180` is False, then excludes all 180 finesse.

  Assumes 100g.
  """
  # Check to see if board_hash and piece is already in cache
  cache_key = (board_hash, piece, no_breaks, can_180)
  
  if cache_key in SIMPLIFICATION_CACHE:
    simplified_hash = SIMPLIFICATION_CACHE[cache_key]
    simplified_key = (simplified_hash, piece, no_breaks, can_180)

    # Get hash transformation function
    simplified_hash = simplified_key[0]
    unsimplify = create_unsimplify(board_hash, simplified_hash)

    # Compute unsimplified hashes
    boards = {}
    for simplified_board in TRANSITION_CACHE[simplified_key]:
      boards[unsimplify(simplified_board)] = TRANSITION_CACHE[simplified_key][simplified_board]

    return boards

  # Ensure piece is valid
  if piece not in PIECES:
    return {}
  
  # Obtain board
  board = unhash_board(board_hash)
  mino_set = set(get_mino_list(board))
  
  # Detect starting position of piece, assuming 100g
  y = get_gravity_y(mino_set, PIECES[piece][0], len(board), 1)
  
  # State is (y, x, rotation)
  queue = deque()
  queue.append(((y, 1, 0), False))  # Base case
  # Set of states visited in queue
  visited = set()
  # (current state, is_spin) -> (previous state, keypress list)
  previous = {}
  previous[((y, 1, 0), False)] = (None, ())  # Base case
  
  # BFS on all possible ending locations for piece, assuming 100g
  while len(queue) > 0:
    current = queue.popleft()
    if current in visited:
      continue
    visited.add(current)
    ((y, x, rotation), is_current_spin) = current
    
    # test movement
    valid_movement_list = ((-1, FINESSE_L), (1, FINESSE_R))
    for (x_move, x_finesse) in valid_movement_list:
      new_y = y
      if is_piece_location_valid(mino_set, PIECES[piece][rotation], y, x + x_move):
        new_y = get_gravity_y(mino_set, PIECES[piece][rotation], y, x + x_move)
        newState = (new_y, x + x_move, rotation)
        queue.append((newState, False))
        if (newState, False) not in previous:
          if new_y != y:
            previous[(newState, False)] = (current, (x_finesse, FINESSE_SD))
          else:
            previous[(newState, False)] = (current, (x_finesse,))
    
    # test rotation
    valid_rotation_list = ((1, FINESSE_CW), (2, FINESSE_180), (3, FINESSE_CCW)) if can_180 else ((1, FINESSE_CW), (3, FINESSE_CCW))
    for (rotation_move, rotation_finesse) in valid_rotation_list:
      new_rotation = (rotation + rotation_move) % 4
      for (kick_offset_y, kick_offset_x) in KICKS[piece][rotation][rotation_move]:
        rotated_y_position = kick_offset_y + y
        rotated_x_position = kick_offset_x + x
        if is_piece_location_valid(mino_set, PIECES[piece][new_rotation], rotated_y_position, rotated_x_position):
          # gravity
          new_y_position = get_gravity_y(mino_set, PIECES[piece][new_rotation], rotated_y_position, rotated_x_position)
          newState = (new_y_position, rotated_x_position, new_rotation)
          if rotated_y_position != new_y_position:
            queue.append((newState, False))
            if (newState, False) not in previous:
              previous[(newState, False)] = (current, (rotation_finesse, FINESSE_SD))
          else:
            # check for spins
            is_spin = is_piece_location_spin(mino_set, piece, new_rotation, new_y_position, rotated_x_position)
            queue.append((newState, is_spin))
            if (newState, is_spin) not in previous:
              previous[(newState, is_spin)] = (current, (rotation_finesse,))
          break
  
  # Obtain board states
  # board_hash -> (is_spin, finesse)
  boards = {}
  for ((y, x, rotation), is_spin) in visited:
    
    new_hash = board_hash
    for (offset_y, offset_x) in PIECES[piece][rotation]:
      new_hash += int(2**(4 * (y + offset_y) + x + offset_x))
    new_board = unhash_board(new_hash)

    # Remove completed lines and check for breaks
    cleared_board = [_ for _ in new_board if 0 in _]
    kept_combo = len(cleared_board) != len(new_board)

    # Check to see if meeting input specs
    if no_breaks and not kept_combo:
      continue
    # Compute finesse
    finesse_groups = []
    current_state = ((y, x, rotation), is_spin)
    while current_state is not None:
      (current_state, finesse_group) = previous[current_state]
      finesse_groups.append(finesse_group)
    finesse = []
    for finesse_group in reversed(finesse_groups):
      finesse += finesse_group
    finesse = tuple(finesse)
    
    cleared_board_hash = hash_board(cleared_board)
    if (
      cleared_board_hash not in boards
      or (is_spin and not boards[cleared_board_hash][0])
      or (is_spin == boards[cleared_board_hash][0] and len(finesse) < len(boards[cleared_board_hash][1]))
    ):
      boards[cleared_board_hash] = (is_spin, finesse)
  
  # Cache results
  simplified_hash = simplify_board_hash(board_hash, piece, no_breaks, can_180, boards)

  # Only need to cache if this is the simplified board
  if board_hash == simplified_hash:
    TRANSITION_CACHE[cache_key] = boards

  return boards

def create_unsimplify(board_hash: BoardHash, simplified_hash: BoardHash
  ) -> Callable[[BoardHash], BoardHash]:
  board_height = len(unhash_board(board_hash))
  simplified_height = len(unhash_board(simplified_hash))
  height_difference = board_height - simplified_height
  height_multiplier = 16 ** height_difference
  hash_difference = board_hash - simplified_hash * height_multiplier
  # Linear transformation of hash
  return lambda h: h * height_multiplier + hash_difference

def simplify_board_hash(
    board_hash: BoardHash,
    piece: Piece,
    no_breaks: bool,
    can_180: bool,
    board_transition: Dict[BoardHash, Tuple[bool, PieceFinesse]]
  ) -> BoardHash:
  """Computes and caches equivalent board hash.
  Finesse and final state will be identical between the two boards aside from adding rows at the bottom."""

  # Key for the cache
  cache_key = (board_hash, piece, no_breaks, can_180)

  # Check to see if board_hash is already in cache
  if cache_key in SIMPLIFICATION_CACHE:
    current_hash = SIMPLIFICATION_CACHE[cache_key]
    return current_hash

  board = unhash_board(board_hash)
  height = len(board)
  hash_factor = 16**height

  # Compute hash of board without given number of bottom rows
  for _ in range(height-1, 0, -1):
    hash_factor //= 16
    candidate_simplified_hash = board_hash//hash_factor
    candidate_cache_key = (candidate_simplified_hash, piece, no_breaks, can_180)
    # Check to see if simplified hash is in tc
    if candidate_cache_key not in TRANSITION_CACHE:
      continue
    candidate_transition = TRANSITION_CACHE[candidate_cache_key]
    # Check to see if number of transitions are the same
    if len(candidate_transition) != len(board_transition):
      continue

    # Check each transition hash for membership in candidate cache
    missing_hash = False
    for board_next_hash in board_transition:
      candidate_next_hash = board_next_hash//hash_factor
      if candidate_next_hash not in candidate_transition:
        missing_hash = True
        break
      if candidate_transition[candidate_next_hash] != board_transition[board_next_hash]:
        missing_hash = True
        break
    if missing_hash:
      continue
    # Candidate verified!
    SIMPLIFICATION_CACHE[cache_key] = candidate_simplified_hash
    return candidate_simplified_hash
  
  # No candidates found.
  SIMPLIFICATION_CACHE[cache_key] = board_hash
  return board_hash

def recompute_caches() -> None:
  """Recomputes caches, removing unneeded entries."""

  # Get list of cache_key values
  keys_to_update = {}
  for cache_key in SIMPLIFICATION_CACHE:
    simplified_hash = SIMPLIFICATION_CACHE[cache_key]
    simplified_key = (simplified_hash, *cache_key[1:])
    if simplified_key not in keys_to_update:
      keys_to_update[simplified_key] = set()
    keys_to_update[simplified_key].add(cache_key)
  
  # print(f"Processing {len(keys_to_update)} keys...", flush = True)
  pruned = 0

  # Recompute each key
  for simplified_key in keys_to_update:
    SIMPLIFICATION_CACHE.pop(simplified_key)
    (s_board_hash, s_piece, s_no_breaks, s_can180) = simplified_key
    new_simplified_hash = simplify_board_hash(s_board_hash, s_piece, s_no_breaks, s_can180, TRANSITION_CACHE[simplified_key])
    # Check if hash remained the same
    if new_simplified_hash == s_board_hash:
      continue
    pruned += 1
    # Remove extraneous transition cache entry
    TRANSITION_CACHE.pop(simplified_key)
    # Update simplification cache keys to point at correct simplified key
    for cache_key in keys_to_update[simplified_key]:
      SIMPLIFICATION_CACHE[cache_key] = new_simplified_hash
  
  # print(f"Pruned {pruned} keys.", flush = True)

def get_next_boards_given_queue(board_hash: BoardHash, queue: Queue) -> List[BoardHash]:
  """Computes all possible board states at the end of the given queue.

  Returns a list of attainable board hashes.

  `board_hash` is the hash of the input board.

  `queue` is a string containing the next pieces.
  """
  boards = set([board_hash])
  for piece in queue:
    new_boards = set()
    for board in boards:
      new_boards = new_boards.union(set(get_next_boards(board, piece).keys()))
    boards = new_boards
  return sorted(boards)

def get_next_board_states(
  input_states: Set[IndexState],
  origins: Dict[IndexState, Set[Tuple[BoardHash, Piece, PieceFinesse]]],
  piece: Piece,
  transitions: Dict[Tuple[BoardHash, Piece], Dict[BoardHash, PieceFinesse]],
  initialize_origins: bool = False
) -> Set[IndexState]:
  """
  Returns the set of reachable next states.

  Also updates initial placements dictionary `origins`, which tracks the starting placements
  from which it is possible to obtain the current state.

  If `initialize_origins` is True, will initialize origins dictionary.
  """
  next_states = set()

  for state in input_states:
    (queue_index, board_hash, hold) = state
    previous_origins = set()
    if state in origins:
      previous_origins = origins[state]
    
    next_state_pieces = [(hold, piece)]
    # Handle holding
    if hold != NULL_PIECE:
      next_state_pieces.append((piece, hold))
    
    for (next_hold, used) in next_state_pieces:
      # Check for valid states
      if (board_hash, used) in transitions:
        # Iterate through each next state
        for next_board_hash in transitions[(board_hash, used)]:
          next_state = (queue_index + 1, next_board_hash, next_hold)
          # Update origins
          if initialize_origins:
            origins[next_state] = set()
            origins[next_state].add((next_board_hash, next_hold, transitions[(board_hash, used)][next_board_hash]))
          else:
            if next_state not in origins:
              origins[next_state] = set()
            origins[next_state] = origins[next_state].union(previous_origins)
          # Update next_states
          next_states.add(next_state)

  return next_states

def get_previous_boards(
    board_hash: BoardHash,
    piece: Piece,
    can_180: bool = True,
  ) -> Dict[BoardHash, tuple[bool, PieceFinesse]]:
  """Computes all possible previous piece boards given board and piece.

  Returns a dictionary of all possible previous boards such that placing the given piece somewhere in the board would result in the given board.

  `board_hash` is the hash of the input board.

  `piece` is the previous piece.

  If `can_180` is False, then excludes all 180 finesse.

  Assumes 100g.
  """
  
  # Obtain board
  board = unhash_board(board_hash)
  
  # Obtain potential board states such that adding the given piece would result in current board state
  candidate_previous_boards = set()
  for line_list in lines_to_insert(len(board), PIECE_WIDTHS[piece]):
    candidate_previous_board = []
    previous_index = 0
    for line_index in line_list:
      for row in range(previous_index, line_index):
        candidate_previous_board.append(board[row])
      candidate_previous_board.append([1, 1, 1, 1])
      previous_index = line_index
    for row in range(previous_index, len(board)):
      candidate_previous_board.append(board[row])
    
    # Look for positions where the given piece fits
    candidate_previous_board_hash = hash_board(candidate_previous_board)
    mino_set = set(get_mino_list(candidate_previous_board))
    for y in range(len(candidate_previous_board)):
      for x in range(4):
        for rotation in range(4):
          is_valid = True
          piece_hash = 0
          for (offset_y, offset_x) in PIECES[piece][rotation]:
            (new_y, new_x) = (y + offset_y, x + offset_x)
            if (new_y, new_x) not in mino_set:
              is_valid = False
              break
            piece_hash += 2**(4 * new_y + new_x)
          
          # Compute hash and check for lack of filled in lines
          if is_valid:
            processed_previous_board_hash = candidate_previous_board_hash - piece_hash
            processed_previous_board = unhash_board(processed_previous_board_hash)
            if False not in [0 in row for row in processed_previous_board]:
              candidate_previous_boards.add(processed_previous_board_hash)
  
  candidate_previous_boards = sorted(candidate_previous_boards)
  # Ensure it is possible to reach current board state from each candidate previous board state
  boards = {}
  for candidate_previous_board in candidate_previous_boards:
    transitions = get_next_boards(candidate_previous_board, piece, can_180=can_180)
    if board_hash in transitions:
      boards[candidate_previous_board] = transitions[board_hash]
  
  return boards

def get_previous_boards_given_queue(board_hash: BoardHash, queue: Queue) -> List[BoardHash]:
  """Computes all possible board states that at the end of the given queue results in the given board.

  Returns a list of starting board hashes.

  `board_hash` is the hash of the input board.

  `queue` is a string containing the previous pieces.
  """
  boards = set([board_hash])
  for piece in reversed(queue):
    prev_boards = set()
    for board in boards:
      prev_boards = prev_boards.union(set(get_previous_boards(board, piece)))
    boards = prev_boards
  return sorted(boards)

def save_caches(filename: str, recompute: bool = True) -> None:
  """Saves `TRANSITION_CACHE` and `SIMPLIFICATION_CACHE` to `pickle`."""
  """Also optionally refactors caches."""
  if recompute:
    recompute_caches()
  with open(filename, 'wb') as output_file:
    pickle.dump((TRANSITION_CACHE, SIMPLIFICATION_CACHE), output_file)

def load_caches(filename: str, recompute: bool = True) -> None:
  """
  Loads `TRANSITION_CACHE` and `SIMPLIFICATION_CACHE` from `pickle`.
  Also optionally refactors caches.
  """
  global TRANSITION_CACHE
  global SIMPLIFICATION_CACHE
  try:
    with open(filename, 'rb') as input_file:
      (TRANSITION_CACHE, SIMPLIFICATION_CACHE) = pickle.load(input_file)
  except (FileNotFoundError, EOFError, pickle.UnpicklingError):
    pass
  if recompute:
    recompute_caches()