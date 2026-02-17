from . import board_lib
from .board_lib import BoardHash, Piece, PieceFinesse, Queue
from .board_lib import EMPTY_BOARD_HASH

from collections import defaultdict, deque
import os
import pickle
import time
from typing import Dict, List, Set, Tuple, TypeAlias

PC_State_Transitions: TypeAlias = Dict[Tuple[BoardHash, Piece], Dict[BoardHash, PieceFinesse]]

# Represents a null save
NULL_SAVE = board_lib.NULL_PIECE

def generate_all_pc_queues(
    filename: str,
    num_pieces: int = 8,
    max_height: int = 8,
    override_existing_file: bool = False
  ) -> Dict[Tuple[Queue, Tuple[BoardHash]], List[PieceFinesse]]:
  """Generate all PC queues with their intermediate states.

  Each line consists of the queue, followed by its intermediate board hashes, followed by the finesse list. For example:

  `TLSZ|305,2097,201|cw;r,sd;f,cw;r,ccw,ccw`

  Arguments:
    `filename` is the name of the file to output to, or read from.
    `num_pieces` is the maximum PC queue length to search for.
    `max_height` is the tallest allowable height of an intermediate state.
    `override_existing_file` if True will generate a new file even if one already exists.
  """
  # (queue, board_list) -> finesse
  pcs = {}

  if not override_existing_file and os.path.isfile(filename):
    with open(filename, 'r') as input_file:
      N = int(input_file.readline().strip())
      pcs = {}
      for _ in range(N):
        (pc_queue, board_hashes, finesse_list) = input_file.readline().strip().split("|")
        board_hashes = tuple(map(int, board_hashes.split(",")))
        finesse_list = [piece_finesse.split(",") for piece_finesse in finesse_list.split(";")]
        pcs[(pc_queue, board_hashes)] = finesse_list
    return pcs
  
  max_height = min(num_pieces, max_height)  # max height
  max_board = 2**(4*max_height) - 1  # max hash
  
  # Optimization: use BFS forwards and backwards
  n_backwards = max(min(num_pieces - 2, 2), num_pieces//4 + 1)
  n_forwards = num_pieces - n_backwards
  
  # Backwards direction
  backwards_queue = deque()
  inital_state = (0, ("", (), ()))  # (board_hash, history)
  backwards_queue.append(inital_state)
  backwards_reachable_states = defaultdict(dict)  # board_hash -> {(queue, board_state_list): finesse}
  backwards_saved_transitions = {}  # (board_hash, piece) -> previous_board_list
  forwards_saved_transitions = {}  # (board_hash, piece) -> next_board_list
  
  visited = set()
  visited.add(inital_state)

  while len(backwards_queue) > 0:
    current = backwards_queue.popleft()
    (board_hash, history) = current
    (history_queue, history_boards, history_finesse) = history

    # Check each possible next piece
    for piece in board_lib.PIECES:
      new_history_queue = piece + history_queue
      if (board_hash, piece) not in backwards_saved_transitions:
        backwards_saved_transitions[(board_hash, piece)] = board_lib.get_previous_boards(board_hash, piece)
      previous_boards = backwards_saved_transitions[(board_hash, piece)]
      # Track reachable board states
      for previous_board in previous_boards:
        (_, finesse) = previous_boards[previous_board]
        new_history_boards = (previous_board, *history_boards)
        new_history_finesse = (finesse, *history_finesse)
        new_history = (new_history_queue, new_history_boards, new_history_finesse)
        if previous_board == 0 or previous_board >= max_board:
          continue
        backwards_reachable_states[previous_board][(new_history_queue, new_history_boards)] = new_history_finesse
        if len(new_history_queue) >= n_backwards:
          continue
        next_state = (previous_board, new_history)
        if next_state in visited:
          continue
        visited.add(next_state)
        backwards_queue.append(next_state)
  
  # Forwards direction
  forwards_queue = deque()
  inital_state = (0, ("", (), ()))  # (board_hash, history)
  forwards_queue.append(inital_state)
  # Dictionary for each board hash all the queues that produce it.
  forwards_reachable_states = defaultdict(dict)  # board_hash -> {(queue, board_state_list): finesse}
  
  visited = set()
  visited.add(inital_state)

  while len(forwards_queue) > 0:
    current = forwards_queue.popleft()
    (board_hash, history) = current
    (history_queue, history_boards, history_finesse) = history
    
    # Check each possible next piece
    for piece in board_lib.PIECES:
      new_history_queue = history_queue + piece
      if (board_hash, piece) not in forwards_saved_transitions:
        forwards_saved_transitions[(board_hash, piece)] = board_lib.get_next_boards(board_hash, piece)
      next_boards = forwards_saved_transitions[(board_hash, piece)]
      # Track reachable board states
      for next_board in next_boards:
        (_, finesse) = next_boards[next_board]
        new_history_boards = (*history_boards, next_board)
        new_history_finesse = (*history_finesse, finesse)
        new_history = (new_history_queue, new_history_boards, new_history_finesse)
        if next_board == 0 or next_board >= max_board:
          continue
        if next_board in backwards_reachable_states:
          forwards_reachable_states[next_board][(new_history_queue, new_history_boards)] = new_history_finesse
        if len(new_history_queue) >= n_forwards:
          continue
        next_state = (next_board, new_history)
        if next_state in visited:
          continue
        visited.add(next_state)
        forwards_queue.append(next_state)
  
  # Merge forwards and backwards
  for board_hash in forwards_reachable_states:
    if board_hash not in backwards_reachable_states:
      continue
    for first_half in forwards_reachable_states[board_hash]:
      for second_half in backwards_reachable_states[board_hash]:
        combined_queue = first_half[0] + second_half[0]
        combined_board_states = first_half[1][:-1] + second_half[1]
        combined_finesse = forwards_reachable_states[board_hash][first_half] + backwards_reachable_states[board_hash][second_half]
        pcs[(combined_queue,combined_board_states)] = combined_finesse
  
  pcs[("I", ())] = [(),]  # Edge case
  
  # Save to output file
  with open(filename, 'w') as output_file:
    pc_list = sorted(pcs.keys(), key = lambda pc: (len(pc[0]), pc[0], pc[1]))
    output_file.write(str(len(pc_list)) + "\n")
    for (pc_queue, pc_hashes) in pc_list:
      finesse_list = pcs[(pc_queue, pc_hashes)]
      finesse_string = ";".join(",".join(str(finesse) for finesse in piece_finesse) for piece_finesse in finesse_list)
      output_file.write(f"{pc_queue}|{','.join(str(pc_hash) for pc_hash in pc_hashes)}|{finesse_string}\n")
  return pcs

def load_pc_queues(filename: str) -> Dict[Tuple[Queue, Tuple[BoardHash]], List[PieceFinesse]]:
  """Reads pc data from file"""
  pcs = {}
  with open(filename, 'r') as input_file:
    N = int(input_file.readline().strip())
    pcs = {}
    # Handle I because it is edge case that is annoying
    input_file.readline()
    pcs[("I", ())] = [(),]
    for _ in range(1, N):
      split_line = input_file.readline().strip().split("|")
      (pc_queue, board_hashes, finesse_list_raw) = split_line
      board_hashes = tuple(map(int, board_hashes.split(",")))
      finesse_list = []
      for piece_finesse_raw in finesse_list_raw.split(";"):
        piece_finesse = tuple(map(int, [finesse for finesse in piece_finesse_raw.split(",") if finesse != ""]))
        finesse_list.append(piece_finesse)
      pcs[(pc_queue, board_hashes)] = finesse_list
  return pcs

# Set of all PCs
PC_SET = set()

def build_pc_set(pcs: Dict[Tuple[Queue, Tuple[BoardHash]], List[PieceFinesse]]) -> Set[Queue]:
  """Returns set of all pcs"""
  global PC_SET
  PC_SET = set()
  for (queue, _) in pcs:
    PC_SET.add(queue)
  return PC_SET

# Board state transition graph
PC_TRANSITIONS = {}

def build_state_transitions(
    pcs: Dict[Tuple[Queue, Tuple[BoardHash]], List[PieceFinesse]]
  ) -> PC_State_Transitions:
  """Builds board state transition graph given pc data.

  Returns, for each input board hash and input piece, all possible resulting board states with the finesse needed.
  """
  global PC_TRANSITIONS
  PC_TRANSITIONS = {}

  # Iterate through each board state sequence
  for board_state_sequence in pcs:
    (queue, board_hash_list) = board_state_sequence
    board_hash_list = list(board_hash_list)
    finesse_list = pcs[board_state_sequence]
    # Add empty board hash for first and last piece
    board_hash_list.append(EMPTY_BOARD_HASH)
    n = len(queue)

    # Iterate through each piece in queue
    for piece_num in range(n):
      initial_state = (board_hash_list[piece_num - 1], queue[piece_num])
      # Check for membership in state transitions
      if initial_state not in PC_TRANSITIONS:
        PC_TRANSITIONS[initial_state] = {}
      # Add finesse
      PC_TRANSITIONS[initial_state][board_hash_list[piece_num]] = finesse_list[piece_num]
  
  return PC_TRANSITIONS

# Maps board hash to minimum pieces to pc in best case
PC_DISTANCES = {}

def build_pc_distances(
    pcs: Dict[Tuple[Queue, Tuple[BoardHash]], List[PieceFinesse]]
  ) -> Dict[BoardHash, int]:
  """Computes, for each board hash, the minimum number of pieces to PC."""
  global PC_DISTANCES
  PC_DISTANCES = {}
  PC_DISTANCES[EMPTY_BOARD_HASH] = 1

  # Iterate through all pc queues
  for (queue, board_hash_list) in pcs:
    n = len(queue)
    # Iterate through all intermediate states
    for piece_num in range(n - 1):
      board_hash = board_hash_list[piece_num]
      distance = n - 1 - piece_num
      # Update distances
      if board_hash not in PC_DISTANCES or PC_DISTANCES[board_hash] > distance:
        PC_DISTANCES[board_hash] = distance
    
  return PC_DISTANCES

def compute_pieces_to_next_pc(transitions: PC_State_Transitions) -> Dict[Tuple[BoardHash, Piece], float]:
  """Computes expected number of pieces before next PC.
  
  Returns, for each pair of board hash and hold piece, the expected number of pieces before the next perfect clear.
  """
  # TODO: HELP HOW DO YOU DO THIS AAAAA
  # For each of 7 next pieces, Minimum of using hold piece and using given piece. Assume infinite vision.
  # For each board hash, look up its location in the tree and then gather all the prefixes to pc.
  # Then compute the average there, using the hold functions too.
  # This will take FOREVER though....
  return {}

def get_pc_saves(piece_queue: Queue) -> Dict[Piece, Queue]:
  """Determines the set of saves for a given piece queue, given set of pcs.

  Returns a dictionary: `{saved_piece : pc_queue}`.
  If `saved_piece` is `NULL_SAVE`, then there is no saved piece at the end: all pieces were used.

  `piece_queue` is a string containing the next pieces.

  `pcs` is the set of all pc queues to consider.
  """
  saves = {}
  for queue_order in board_lib.get_queue_orders(piece_queue):
    if queue_order[:-1] in PC_SET:
      saves[queue_order[-1]] = queue_order[:-1]
    if queue_order in PC_SET:
      saves[NULL_SAVE] = queue_order
  return saves

def get_max_pc_states(
    pc_states: Set[Tuple[int, Piece]],
    piece_queue: Queue,
    track_first: bool = False
  ) -> Dict[Tuple[int, Piece], Tuple[int, Tuple[int, Piece] | Set[Tuple[int, Piece]], Queue]]:
  """
  Returns dictionary mapping queue index and hold piece to most number of pcs obtained with that result.

  If `track_first` is True, will track the initial placement instead of previous.
  """
  # Length of longest pc
  max_n = len(max(PC_SET, key = lambda _:len(_)))
  piece_queue = piece_queue + NULL_SAVE

  # (index, hold piece) -> (num pcs, previous state, previous solve)
  most_pcs_at_state = {}
  for pc_state in pc_states:
    initial_tracked = None
    if track_first:
      initial_tracked = set([pc_state,])
    most_pcs_at_state[pc_state] = (0, initial_tracked, None)
  
  # Loop through each index
  for index in range(1, len(piece_queue)):

    # Loop through each possible hold piece
    for hold in board_lib.PIECES:
      current_state = (index, hold)
      if current_state not in most_pcs_at_state:
        # Current state is not reached
        continue
      
      # Ensure we don't use more pieces than length of queue
      max_pieces_used = min(max_n, len(piece_queue) - index)
      for pieces_used in range(1, max_pieces_used + 1):

        # The effective pc queue
        pc_queue = hold + piece_queue[index:index + pieces_used]
        saves = get_pc_saves(pc_queue)
        for save in saves:
          next_state = (index + pieces_used, save)

          # Check to see if most_pcs_at_state should be updated
          new_num_pcs = most_pcs_at_state[current_state][0] + 1
          tracked_item = current_state
          if next_state not in most_pcs_at_state or new_num_pcs > most_pcs_at_state[next_state][0]:
            if track_first:
              tracked_item = most_pcs_at_state[current_state][1]
            most_pcs_at_state[next_state] = (new_num_pcs, tracked_item, saves[save])
          elif new_num_pcs == most_pcs_at_state[next_state][0]:
            tracked_item = current_state
            if track_first:
              tracked_item = most_pcs_at_state[next_state][1].union(most_pcs_at_state[current_state][1])
            most_pcs_at_state[next_state] = (new_num_pcs, tracked_item, saves[save])
  
  return most_pcs_at_state

def max_pcs_in_queue(piece_queue: Queue) -> Tuple[int, List[Queue]]:
  """Computes the maximum number of pcs that can be obtained in the given queue, and the list of PCs taken.
  """
  # Add terminator character to allow for using whole queue
  piece_queue = piece_queue + NULL_SAVE

  # Set of initial pcs
  pc_states = set()
  pc_states.add((1, piece_queue[0]))
  # (index, hold piece) -> (num pcs, previous state, previous solve)
  most_pcs_at_state = get_max_pc_states(pc_states, piece_queue)
  
  # Best state
  (max_pcs, current_state, prev_solve) = max(most_pcs_at_state.values())

  # No pcs found :(
  if max_pcs == 0:
    return (0, [])
  
  assert type(current_state) is tuple, "something went horribly wrong"

  # Generate pc history
  reversed_history = [prev_solve,]
  # TODO: Figure out why typechecker is screaming at me. consider duplicating code
  while most_pcs_at_state[current_state][2] is not None:
    reversed_history.append(most_pcs_at_state[current_state][2])
    current_state = most_pcs_at_state[current_state][1]
  history = list(reversed(reversed_history))
  return (max_pcs, history)

# Map of state to foresight score set
# different files for different N (of PC set) and foresight
# [(hash, hold_piece, can_hold)] -> (foresight_queue -> score)
PC_FORESIGHT_CACHE = {}

def compute_foresight_scores(
    final_states: List[Tuple[int, BoardHash, Piece]],
    foresight: int = 1,
    can_hold: bool = True
) -> Dict[Tuple[int, BoardHash, Piece], Dict[Queue, int]]:
  """Given ending states and num foresight pieces, returns a dictionary mapping each ending state and foresight queue to its best score"""
  global PC_FORESIGHT_CACHE
  
  max_foresight_score = foresight + max(PC_DISTANCES.values()) + 3
  foresight_scores = {}
  
  # Uncached states
  new_final_states = []
  cached_final_states = []

  # Initialize foresight_scores
  for final_state in final_states:
    # Skip cached states
    if (*final_state[1:], can_hold) in PC_FORESIGHT_CACHE:
      cached_final_states.append(final_state)
      continue
    foresight_scores[final_state] = {}
    new_final_states.append(final_state)

  # Look at each foresight queue
  for foresight_queue in board_lib.all_queues(foresight):
    # (foresight_queue_index, board_hash, hold) -> set(final_state)
    # Maps foresight states to set of final_state
    foresight_first_placements = defaultdict(set)

    # Similar to continuation_queues but for foresight
    foresight_continuation_queues = defaultdict(set)

    # Initialize states
    for final_state in new_final_states:
      foresight_continuation_queues[0].add(final_state)
      foresight_first_placements[final_state].add(final_state)
      foresight_scores[final_state][foresight_queue] = max_foresight_score

    # BFS to play entire queue without hold
    for piece_num in range(foresight):
      piece = foresight_queue[piece_num]
      next_states = board_lib.get_next_board_states(
        foresight_continuation_queues[piece_num],
        foresight_first_placements,
        piece,
        PC_TRANSITIONS
      )
    
      # Update pc distances
      for state in next_states:
        if state[1] != EMPTY_BOARD_HASH:
          foresight_continuation_queues[piece_num + 1].add(state)
          continue
        for final_state in foresight_first_placements[state]:
          # Score is number of pieces placed
          new_score = min(foresight_scores[final_state][foresight_queue], piece_num + 1)
          foresight_scores[final_state][foresight_queue] = new_score
    
    # Update pc distances of states that did not reach pc
    for state in foresight_continuation_queues[foresight]:
      for final_state in foresight_first_placements[state]:
        # Score is min distance from a pc
        score = foresight + PC_DISTANCES[final_state[1]]
        new_score = min(foresight_scores[final_state][foresight_queue], score)
        foresight_scores[final_state][foresight_queue] = new_score

  if not can_hold:
    # Add to cache
    for final_state in foresight_scores:
      PC_FORESIGHT_CACHE[(final_state[1], final_state[2], can_hold)] = foresight_scores[final_state]
    # Augment with cached results
    for final_state in cached_final_states:
      foresight_scores[final_state] = PC_FORESIGHT_CACHE[(final_state[1], final_state[2], can_hold)]
    return foresight_scores
  
  # Compute combined scores for all final states
  foresight_scores_with_hold = {}

  # For each final state and foresight queue
  for final_state in foresight_scores:
    (queue_index, board_hash, hold) = final_state
    foresight_scores_with_hold[final_state] = {}

    for foresight_queue in board_lib.all_queues(foresight):
      combined_queue = hold + foresight_queue

      # Compute best score with hold
      best_score = max_foresight_score
      for queue_order in board_lib.get_queue_orders(combined_queue):
        best_score = min(best_score, foresight_scores[final_state][queue_order[:-1]])
      # Update score
      foresight_scores_with_hold[final_state][foresight_queue] = best_score

  # Add to cache
  for final_state in foresight_scores_with_hold:
    PC_FORESIGHT_CACHE[(final_state[1], final_state[2], can_hold)] = foresight_scores_with_hold[final_state]
  # Augment with cached results
  for final_state in cached_final_states:
    foresight_scores_with_hold[final_state] = PC_FORESIGHT_CACHE[(final_state[1], final_state[2], can_hold)]

  return foresight_scores_with_hold

def get_best_next_pc_state(
    board_hash: BoardHash,
    queue: Queue,
    foresight: int = 1,
    can_hold: bool = True
  ) -> Tuple[BoardHash, Piece, PieceFinesse]:
  """Computes best next board state: `(boardhash, hold, finesse)`

  First, attempts to maximize expected number of pcs over next `len(queue) - 1 + foresight` pieces.
  Among those, minimizes the minimum distance from next pc.

  Returns a tuple with the next board hash, piece used, and finesse.

  `board_hash` is the hash of the input board.

  `queue` is a string containing the hold piece followed by the next pieces.

  `pc_set` is a set of all PC queues, the universe of possible PCs.

  `transitions` is the pc state transitions dictionary, the universe of possible moves.

  `pc_distances` maps board hashes to the minimum pieces required to PC.

  If `can_hold` is False, then assumes that the hold queue is empty and disallows access to it.
  """
  # Handle nohold
  if not can_hold:
    queue = NULL_SAVE + queue

  # (queue_index, board_hash, hold) -> set((board_hash, hold, finesse))
  # For each board state, set of the initial states that could have generated the state
  first_placements = defaultdict(set)

  hold = queue[0]
  # Map piece number to state
  continuation_queues = defaultdict(set)
  # Initial state
  initial_state = (1, board_hash, queue[0])
  continuation_queues[1].add(initial_state)
  # Stores if a pc has been found
  can_pc = False
  # Set of states where there is a pc
  pc_states = set()

  # BFS to find moves that produce empty boards
  for queue_index in range(1, len(queue)):
    # Obtain next states
    next_states = board_lib.get_next_board_states(
      continuation_queues[queue_index],
      first_placements,
      queue[queue_index],
      PC_TRANSITIONS,
      (queue_index == 1)
    )
    for state in next_states:
      # Check if pc
      if state[1] == EMPTY_BOARD_HASH:
        can_pc = True
        (index, _, hold) = state
        pc_states.add((index, hold))
        continue
      continuation_queues[queue_index + 1].add(state)

  if can_pc:
    # Using other function, off by one because not accounting for first pc
    most_pcs_at_state = get_max_pc_states(pc_states, queue, True)
    # Remove states with null saves
    to_remove = []
    for (index, hold) in most_pcs_at_state:
      if hold == NULL_SAVE:
        to_remove.append((index, hold))
    for removed_state in to_remove:
      most_pcs_at_state.pop(removed_state)
    # Compute num_max_pcs
    num_max_pcs = 0
    for (index, hold) in most_pcs_at_state:
      num_max_pcs = max(most_pcs_at_state[(index, hold)][0], num_max_pcs)
    
    # Map piece number to state
    max_pc_continuation_queues = defaultdict(set)
    # For each board state, set of the initial states that could have generated the state
    max_pc_first_placements = defaultdict(set)

    # Initial states
    for (index, hold) in most_pcs_at_state:
      # Check if using max pcs
      if most_pcs_at_state[(index, hold)][0] != num_max_pcs:
        continue
      # Initialize states
      max_pc_continuation_queues[index].add((index, 0, hold))
      max_pc_first_placements[(index, 0, hold)] = most_pcs_at_state[(index, hold)][1]

    # BFS until end
    for queue_index in range(1, len(queue)):
      # Obtain next states
      next_states = board_lib.get_next_board_states(
        max_pc_continuation_queues[queue_index],
        max_pc_first_placements,
        queue[queue_index],
        PC_TRANSITIONS
      )
      for state in next_states:
        # Check if pc
        if state[1] == EMPTY_BOARD_HASH:
          # TODO: figure out what to do in this case
          # getting here means we found a pc that wasn't in the set, like accidentally stumbling on a pc
          # so in spirit of not knowing that pc exists we won't think it pcs.
          # continue
          pass
        max_pc_continuation_queues[queue_index + 1].add(state)
    
    # Update first placements
    new_first_placements = {}
    
    # Iterate through all final states of max_pc
    for final_state in max_pc_first_placements:
      (queue_index, _, _) = final_state
      # Ignore states that are not at the end
      if queue_index != len(queue):
        continue
      # Add all corresponding first placements from first pc state
      new_first_placements[final_state] = set()
      for (index, hold) in max_pc_first_placements[final_state]:
        first_pc_state = (index, 0, hold)
        new_first_placements[final_state] = new_first_placements[final_state].union(first_placements[first_pc_state])
    first_placements = new_first_placements

  # Construct set of states reachable from first placements
  # (board_hash, hold) -> set((queue_index, board_hash, hold))
  reachables = defaultdict(set)
  max_foresight_score = foresight + max(PC_DISTANCES.values()) + 3
  # score is sum of min number of pieces to pc for each foresight queue
  # maps final state and queue to foresight score
  final_states = []

  # Build reachables
  for final_state in first_placements:
    (queue_index, _, _) = final_state
    # Ignore states that are not at the end
    if queue_index != len(queue):
      continue
    # Map from foresight queue to score
    final_states.append(final_state)
    # Add final state as a reachable state to each first_state
    for first_state in first_placements[final_state]:
      reachables[first_state].add(final_state)
  
  # Obtain foresight scores
  foresight_scores = compute_foresight_scores(
    final_states,
    foresight,
    can_hold
  )
  
  # Compute combined scores for all initial states
  best_initial_score_sum = max_foresight_score * 7 ** foresight
  best_initial_state = (EMPTY_BOARD_HASH, NULL_SAVE, board_lib.NULL_FINESSE)

  # For every initial state
  for first_state in reachables:
    initial_score_sum = 0
    # For each foresight queue
    for foresight_queue in board_lib.all_queues(foresight):
      # Compute the best score of any reachable final state
      best_score = max_foresight_score
      for final_state in reachables[first_state]:
        best_score = min(best_score, foresight_scores[final_state][foresight_queue])
      # Update score sum
      initial_score_sum += best_score
  
    # Test if this is a better state
    if initial_score_sum < best_initial_score_sum:
      best_initial_score_sum = initial_score_sum
      best_initial_state = first_state

  return best_initial_state

# inf pc simulator
# simulation_length is number of pieces to simulate
def simulate_inf_pc(pc_filename: str, simulation_length: int = 1000, pc_n: int = 6, lookahead: int = 6, foresight: int = 1, canHold: bool = True, pc_cache_filename: str | None = None, starting_state: int = 0) -> list[tuple[str, int]]:
  """Infinite pc simulator.

  Prints a simulation of the pc decisions taken.

  `simulation_length` is number of pieces to simulate.

  `lookahead` is the number of pieces to consider at a time for computation.

  `foresight` is the length of the foresight queue.
  This is used to account for the next `foresight` pieces.
  This is then accounted for when selecting a continuation.

  If `canHold` is False, then assumes that the hold queue is empty and disallows access to it.

  `tc_cache_filename` is the file name of the transition cache to load or save from.
  If `tc_cache_filename` is None, will not save the cache at the end.

  `starting_state` is the hash of the intial board state.
  """
  pieces = board_lib.generate_7bag()
  pc_decisions = []
  pc_numbers = []

  # initialize game state
  current_hash = starting_state
  hold = next(pieces)
  window = ""
  for _ in range(lookahead):
    window += next(pieces)
  num_pcs = 0
  
  if pc_cache_filename is not None:
    load_pc_foresight_cache(pc_cache_filename, pc_n, foresight)

  pc_data = load_pc_queues(pc_filename)
  build_pc_set(pc_data)
  build_state_transitions(pc_data)
  build_pc_distances(pc_data)

  time_sum = 0
  time_num = 0
  current_pc = ""
  for decision_num in range(simulation_length):
    # compute next state
    next_queue = hold + window if canHold else window
    time_start = time.time()

    #try:
    next_state = get_best_next_pc_state(current_hash, next_queue, foresight, canHold)
    #except:
      #board_lib.save_caches("data/corrupted")
      #break
    time_elapsed = time.time() - time_start
    time_sum += time_elapsed
    time_num += 1
    (current_hash, next_hold, finesse) = next_state
    used = window[0] if next_hold == hold else hold
    current_pc += used
    hold = next_hold

    # compute next window
    window = window[1:] + next(pieces)

    # handle pc logic
    if current_hash == EMPTY_BOARD_HASH:
      num_pcs += 1
      pc_numbers.append(len(current_pc))
      pc_decisions.append(current_pc)
      current_pc = ""
    
    # display board and game state
    board_lib.display_board(current_hash)
    print(f"Used {used}, next pieces [{hold}]{window}")
    print(f"Finesse: {finesse}")
    print(f"pc/p: {round(num_pcs/time_num, 4)}, pps = {round(1/time_elapsed, 2)}")
  
  # print(f"Average pc length: {sum([_*_ for _ in pc_numbers]) / sum(pc_numbers)}")
  print(f"Average pieces per pc: {sum(pc_numbers) / len(pc_numbers)}")
  print(f"Average pps: {time_num / time_sum}")

  if pc_cache_filename is not None:
    save_pc_foresight_cache(pc_cache_filename, pc_n, foresight)
  
  return pc_decisions

def save_pc_foresight_cache(base_filename: str, pc_n: int, foresight: int) -> None:
  """Saves `PC_FORESIGHT_CACHE` to `pickle`."""
  """Also optionally refactors caches."""
  with open(f"{base_filename}_{pc_n}_{foresight}", 'wb') as output_file:
    pickle.dump(PC_FORESIGHT_CACHE, output_file)

def load_pc_foresight_cache(folder: str, pc_n: int, foresight: int) -> None:
  """
  Loads `PC_FORESIGHT_CACHE` and `SIMPLIFICATION_CACHE` from `pickle`.
  Also optionally refactors caches.
  """
  global PC_FORESIGHT_CACHE
  try:
    with open(f"{folder}/{pc_n}_{foresight}", 'rb') as input_file:
      PC_FORESIGHT_CACHE = pickle.load(input_file)
  except (FileNotFoundError, EOFError, pickle.UnpicklingError):
    pass