from . import board_lib
from .board_lib import BoardHash, IndexState, Piece, PieceFinesse, Queue
from collections import defaultdict
import random
import time
from typing import Dict, List, Set, Tuple

def get_next_combo_states(
  input_states: Set[IndexState],
  origins: Dict[IndexState, Dict[Tuple[BoardHash, Piece, PieceFinesse], int]],
  piece: Piece,
  no_breaks: bool = True,
  can_180: bool = True,
  initialize_origins: bool = False
) -> Set[IndexState]:
  """
  Returns the set of reachable next states, assuming no breaks.

  Also updates initial placements dictionary `origins`, which tracks the starting placements
  from which it is possible to obtain the current state.

  If `initialize_origins` is True, will initialize origins dictionary.
  """
  next_states = set()

  for state in input_states:
    (queue_index, board_hash, hold) = state
    current_mino_count = board_lib.num_minos(board_hash)

    previous_origins = {}
    if state in origins:
      previous_origins = origins[state]
    
    next_state_pieces = [(hold, piece)]
    # Handle holding
    if hold != board_lib.NULL_PIECE:
      next_state_pieces.append((piece, hold))
    
    for (next_hold, used) in next_state_pieces:
      transitions = board_lib.get_next_boards(board_hash, used, no_breaks, can_180)
      
      for next_board_hash in transitions:
        # If no_breaks is False, we only want moves with breaks
        broken = board_lib.num_minos(next_board_hash) > current_mino_count
        if not no_breaks and not broken:
          continue
        next_state = (queue_index + 1, next_board_hash, next_hold)
        origins_key = (next_board_hash, next_hold, transitions[next_board_hash][1])
        spins_added = int(transitions[next_board_hash][0])
        # Update origins
        if initialize_origins:
          origins[next_state] = {}
          origins[next_state][origins_key] = spins_added
        else:
          if next_state not in origins:
            origins[next_state] = {}
          for previous_origins_key in previous_origins:
            # Compute new best num spins
            new_num_spins = previous_origins[previous_origins_key] + spins_added
            # Update number of spins
            if previous_origins_key not in origins[next_state]:
              origins[next_state][previous_origins_key] = 0
            if origins[next_state][previous_origins_key] < new_num_spins:
              origins[next_state][previous_origins_key] = new_num_spins
        # Update next_states
        next_states.add(next_state)

  return next_states

MAX_FORESIGHT_SCORE = int(1e18)
FORESIGHT_BREAK_SCORE = int(1e9)
MINO_COUNT_SCORE_MULTIPLIER = 100

def compute_combo_foresight_scores(
    final_states: List[IndexState],
    foresight: int = 1,
    can_180: bool = True,
    can_hold: bool = True
) -> Dict[IndexState, Dict[Queue, int]]:
  """
  Returns a dictionary mapping each ending state and foresight queue to foresight score
  """
  foresight_scores = {}
  # Initialize foresight_scores
  for final_state in final_states:
    foresight_scores[final_state] = {}

  # Look at each foresight queue
  for foresight_queue in board_lib.all_queues(foresight):
    # (foresight_queue_index, board_hash, hold) -> {final_state -> numspins}
    # Maps foresight states to set of final_state
    foresight_first_placements = {}

    # Similar to continuation_queues but for foresight
    foresight_continuation_queues = defaultdict(set)

    # Initialize states
    for final_state in final_states:
      foresight_continuation_queues[0].add(final_state)
      foresight_first_placements[final_state] = {final_state: 0}
      foresight_scores[final_state][foresight_queue] = FORESIGHT_BREAK_SCORE

    # BFS to play entire queue without hold
    for piece_num in range(foresight):
      piece = foresight_queue[piece_num]
      next_states = get_next_combo_states(
        foresight_continuation_queues[piece_num],
        foresight_first_placements,
        piece,
        True,
        can_180,
        False
      )
    
      # Add to queue
      for state in next_states:
        foresight_continuation_queues[piece_num + 1].add(state)
    
    # Update num_breaks of states that finished queue
    for final_foresight_state in foresight_continuation_queues[foresight]:
      mino_count = board_lib.num_minos(final_foresight_state[1])
      for final_state in foresight_first_placements[final_foresight_state]:
        foresight_score = 0
        # mino portion
        foresight_score += board_lib.score_num_minos(mino_count) * MINO_COUNT_SCORE_MULTIPLIER
        # spins portion
        foresight_score -= foresight_first_placements[final_foresight_state][final_state]
        foresight_scores[final_state][foresight_queue] = min(foresight_score, foresight_scores[final_state][foresight_queue])

  # If no hold we are done
  if not can_hold:
    return foresight_scores
  
  # Compute combined scores for all final states
  foresight_scores_with_hold = {}

  # For each final state and foresight queue
  for final_state in foresight_scores:
    (queue_index, board_hash, hold) = final_state
    foresight_scores_with_hold[final_state] = {}

    for foresight_queue in board_lib.all_queues(foresight):
      combined_queue = foresight_queue
      if hold != board_lib.NULL_PIECE:
        combined_queue = hold + foresight_queue

      # Compute best score with hold
      best_score = MAX_FORESIGHT_SCORE
      for queue_order in board_lib.get_queue_orders(combined_queue):
        best_score = min(best_score, foresight_scores[final_state][queue_order[:foresight]])
      # Update score
      foresight_scores_with_hold[final_state][foresight_queue] = best_score

  return foresight_scores_with_hold

def get_best_next_combo_state(
  board_hash: BoardHash,
  queue: Queue,
  foresight: int = 1,
  can_180: bool = True,
  can_hold: bool = True,
  build_up_now: bool = False
) -> Tuple[BoardHash, Piece, PieceFinesse]:
  """Computes best next board state.

  First, attempts to minimize number of placements over the next `len(queue) - 1` pieces that do not clear a line.
  Among those, minimizes the number of minos on the board.

  Returns a tuple with the piece used and the next board hash.

  `board_hash` is the hash of the input board.

  `queue` is a string containing the hold piece followed by the next pieces.

  `foresight` is the length of the foresight queue.
  This is used to compute the probability that the next `foresight` pieces will force a non line clear.
  This is then accounted for when selecting a continuation.

  If `can_hold` is False, then assumes that the hold queue is empty and disallows access to it.

  If `build_up_now` is True, then will prioritize upstacking to 12 minos over not breaking.
  """
  # Handle nohold
  if not can_hold:
    queue = board_lib.NULL_PIECE + queue

  # Handle build_up_now
  num_building_steps = max(0, (15 - board_lib.num_minos(board_hash)) // 4)
  if not build_up_now:
    # If we are not upstacking, set num upstacking steps to 0
    num_building_steps = 0

  # (queue_index, board_hash, hold) -> {(starting_board_hash, hold, finesse) -> num_spins}
  first_placements = {}
  
  # Initial state
  hold = queue[0]
  initial_state = (1, board_hash, hold)

  # Map piece number to state
  continuation_queues = defaultdict(set)
  continuation_queues[1].add(initial_state)

  visited_states = set()

  """Step 1: Get ending states"""
  for num_breaks in range(len(queue)+1):

    # Only do this step if done upstacking
    if num_breaks >= num_building_steps:
      for queue_index in range(1, len(queue)):
        # Obtain next states
        next_states = get_next_combo_states(
          continuation_queues[queue_index],
          first_placements,
          queue[queue_index],
          True,
          can_180,
          (queue_index == 1)
        )
        for state in next_states:
          # Check if already visited (from previous iteration)
          if state in visited_states:
            continue
          # Add to queue
          continuation_queues[queue_index + 1].add(state)
          # Add to visited
          visited_states.add(state)
    
    # Check if we made it to the end of the queue
    if len(continuation_queues[len(queue)]) > 0:
      break

    # Add one break. Reinitialize continuation_queues
    new_continuation_queues = defaultdict(set)
    for queue_index in range(1, len(queue)):
      # Obtain next states
      next_states = get_next_combo_states(
        continuation_queues[queue_index],
        first_placements,
        queue[queue_index],
        False,
        can_180,
        (queue_index == 1)
      )
      for state in next_states:
        # Add to queue
        new_continuation_queues[queue_index + 1].add(state)
    continuation_queues = new_continuation_queues

  """Step 2: Compute set of ending states for each starting state"""
  final_states = list(continuation_queues[len(queue)])
  # (board_hash, hold, finesse) -> {(queue_index, board_hash, hold) -> num_spins}
  reachables = {}
  # Build reachables
  for final_state in final_states:
    # Add final state as a reachable state to each first_state
    for first_state in first_placements[final_state]:
      if first_state not in reachables:
        reachables[first_state] = {}
      reachables[first_state][final_state] = first_placements[final_state][first_state]
  
  # Best first state
  best_first_state = (board_lib.EMPTY_BOARD_HASH, board_lib.NULL_PIECE, (board_lib.FINESSE_HOLD,))
  best_score = MAX_FORESIGHT_SCORE

  """Step 2.5: Handle foresight == 0"""
  if foresight == 0:
    # Pick the state with the best mino count and most spins
    for first_state in reachables:
      score = best_score + 1
      # Compute first state score
      for final_state in reachables[first_state]:
        (queue_index, final_board_hash, hold) = final_state
        final_state_score = 0
        # mino count portion
        mino_count = board_lib.num_minos(final_board_hash)
        final_state_score += board_lib.score_num_minos(mino_count) * len(queue)
        # spins portion
        final_state_score -= reachables[first_state][final_state]
        # Update first state score
        score = min(score, final_state_score)
      
      # Update overall best state
      if score < best_score:
        best_score = score
        best_first_state = first_state
    
    # return best next state
    return best_first_state
  
  """Step 3: Handle foresight"""
  # Obtain foresight scores
  foresight_scores = compute_combo_foresight_scores(
    final_states,
    foresight,
    can_180,
    can_hold
  )
  
  """Step 4: Select best continuation"""
  # For every initial state
  for first_state in reachables:
    # Compute foresight portion
    initial_score_sum = 0
    # For each foresight queue
    for foresight_queue in board_lib.all_queues(foresight):
      # Compute the best score of any reachable final state
      foresight_score = 1000000
      for final_state in reachables[first_state]:
        adjusted_foresight_score = foresight_scores[final_state][foresight_queue]
        # spins correction
        adjusted_foresight_score -= first_placements[final_state][first_state]
        # update best score
        foresight_score = min(foresight_score, adjusted_foresight_score)
      # Update score sum
      initial_score_sum += foresight_score
  
    # Test if this is a better state
    if initial_score_sum < best_score:
      best_score = initial_score_sum
      best_first_state = first_state

  # return best next state
  return best_first_state

def get_break_probability(board_hash: int, queue: str, foresight: int = 1, can_180: bool = True, canHold: bool = True) -> float:
  """Computes probability of combo break given queue and foresight."""
  return 0  # TODO: REAL function

def get_best_combo_continuation(board_hash: int, queue: str, lookahead: int = 6, foresight: int = 1, can_180: bool = True, canHold: bool = True, finish: bool = True) -> list[tuple[str, int]]:
  """Computes best combo continuation, placing `len(queue) - lookahead` pieces.

  `board_hash` is the hash of the input board.

  `queue` is a string containing the hold piece followed by the next pieces.

  `lookahead` is the number of pieces to consider at a time for computation.

  `foresight` is the length of the foresight queue.
  This is used to compute the probability that the next `foresight` pieces will force a non line clear.
  This is then accounted for when selecting a continuation.

  If `can_180` is False, then excludes all 180 finesse.

  If `canHold` is False, then assumes that the hold queue is empty and disallows access to it.

  If `finish` is True, will attempt to place an additional `lookahead - 1` pieces, exhausting the queue.
  However, without more information, the placements at the end may not be optimal.
  """
  combo = []
  current_hash = board_hash
  hold = queue[0]
  window = queue[1:lookahead+1]

  for decision_num in range(len(queue) - 1):
    # compute next state
    next_state = get_best_next_combo_state(current_hash, hold + window, foresight, can_180, canHold)
    (current_hash, hold, finesse) = next_state
    combo.append(next_state)

    # compute next window
    if decision_num < len(queue) - lookahead - 1:
      window = window[1:]+queue[decision_num+lookahead+1]
    elif not finish:
      # no need to finish the queue off
      break
    else:
      window = window[1:]
    
  return combo

def simulate_inf_ds(simulation_length: int = 1000, lookahead: int = 6, foresight: int = 1, well_height: int = 8, can_hold: bool = True, tc_cache_filename: str | None = None, starting_state: int = 0) -> list[tuple[str, int]]:
  """Infinite downstack simulator.

  Prints a simulation of the combo decisions taken.

  `simulation_length` is number of pieces to simulate.

  `lookahead` is the number of pieces to consider at a time for computation.

  `foresight` is the length of the foresight queue.
  This is used to compute the probability that the next `foresight` pieces will force a non line clear.
  This is then accounted for when selecting a continuation.

  `well_height` is the amount of garbage to add underneath the stack whenever a piece is placed that does not clear a line.

  If `can_hold` is False, then assumes that the hold queue is empty and disallows access to it.

  `tc_cache_filename` is the file name of the transition cache to load or save from.
  If `tc_cache_filename` is None, will not save the cache at the end.

  `starting_state` is the hash of the intial board state.
  """
  pieces = board_lib.generate_7bag()
  combo_decisions = []
  combo_numbers = []

  # initialize game state
  max_hash = 0
  current_hash = starting_state
  current_minos = board_lib.num_minos(starting_state)
  hold = next(pieces)
  window = ""
  for _ in range(lookahead):
    window += next(pieces)
  current_combo = 0

  # precompute garbage wells
  well_multiplier = (16**well_height - 1)//15
  wells = [row_code * well_multiplier for row_code in [7, 11, 13, 14]]
  
  if tc_cache_filename is not None:
    board_lib.load_caches(tc_cache_filename, True)

  time_sum = 0
  time_num = 0
  for decision_num in range(simulation_length):
    # compute next state
    num_minos = board_lib.num_minos(current_hash)
    upstack = (num_minos in [0, 1, 2, 4, 5])
    next_queue = hold + window if can_hold else window
    time_start = time.time()

    next_state = get_best_next_combo_state(current_hash, next_queue, foresight, build_up_now=upstack, can_hold=can_hold)
    time_elapsed = time.time() - time_start
    time_sum += time_elapsed
    time_num += 1
    (current_hash, next_hold, finesse) = next_state
    used = window[0] if next_hold == hold else hold
    hold = next_hold
    combo_decisions.append(next_state)

    # compute next window
    window = window[1:] + next(pieces)

    # handle combo logic
    minos = board_lib.num_minos(current_hash)
    if minos <= current_minos:
      current_combo += 1
      current_minos = minos
    else:
      combo_numbers.append(current_combo)
      current_combo = 0
      current_minos = minos + 3 * well_height

      # add garbage!!!
      current_hash = current_hash * int(16**well_height) + wells[random.randint(0, 3)]
    
    # display board and game state
    board_lib.display_board(current_hash)
    print(f"Combo: {current_combo}, pps = {round(1/time_elapsed, 2)}")
    print(f"Used {used}, next pieces [{hold}]{window}")
    print(f"Finesse: {finesse}")

    max_hash = max(max_hash, current_hash)
    if max_hash > 16**27:
      print(f"DEAD after {decision_num} pieces")
      break
  combo_numbers.append(current_combo)
  print(combo_numbers)
  height = 0
  while max_hash > 0:
    max_hash //= 16
    height += 1
  print(f"Max height: {height}")
  print(f"Average combo: {sum([_*_ for _ in combo_numbers]) / sum(combo_numbers)}")
  print(f"Average pps: {time_num / time_sum}")

  if tc_cache_filename is not None:
    board_lib.save_caches(tc_cache_filename)

  return combo_decisions