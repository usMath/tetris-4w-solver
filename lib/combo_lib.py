import lib.board_lib as board_lib
from lib.board_lib import Board, BoardHash, Coordinate, CoordinateList, CoordinateSet, Finesse, Piece, PieceFinesse, Queue
from collections import defaultdict, deque
import random
import time
from typing import Dict, List, Optional, Set, Tuple, TypeAlias

# Computes best next board state for board state sequence
# that results in the fewest non line clears
# if len(queue) - 1 pieces are placed
# Among those, the one with the fewest minos
# Returns the piece used and the next board hash
# If build_up_now is True, then will prioritize upstacking to target minos over not breaking
def get_best_next_combo_state(board_hash: int, queue: str, foresight: int = 1, can180: bool = True, canHold: bool = True, build_up_now: bool = False, foresight_cache: dict | None = None) -> tuple[str, int]:
  """Computes best next board state.

  First, attempts to minimize number of placements over the next `len(queue) - 1` pieces that do not clear a line.
  Among those, minimizes the number of minos on the board.

  Returns a tuple with the piece used and the next board hash.

  `board_hash` is the hash of the input board.

  `queue` is a string containing the hold piece followed by the next pieces.

  `foresight` is the length of the foresight queue.
  This is used to compute the probability that the next `foresight` pieces will force a non line clear.
  This is then accounted for when selecting a continuation.

  If `can180` is False, then excludes all 180 finesse.

  If `canHold` is False, then assumes that the hold queue is empty and disallows access to it.

  If `build_up_now` is True, then will prioritize upstacking to target number of minos over not breaking.
  """
  if foresight_cache is None:
    foresight_cache = {}

  # edit for holding
  if not canHold:
    # add an invalid piece to start of queue
    queue = "?" + queue
  
  BREAKS_LIMIT = len(queue) # ignore anything with more than BREAKS_LIMIT breaks

  # (hold, board_state) -> {(hold, queue_index, ending_board_state) -> num_spins}
  immediate_placements = {}
  # (hold, queue_index, board_state) -> {(hold, starting_board_state) -> num_spins}
  reversed_immediate_placements = {}
  # (hold, queue_index, board_state) -> (combo breaks, num_spins)
  least_breaks = {}

  best_end_state = None
  for max_breaks in range(BREAKS_LIMIT+1):
    
    # Track what we have explored.
    states_considered = set()

    # queue_index -> list of (hold, board_state)
    continuation_queues = defaultdict(list)

    # make max_breaks > 0 faster by using results from max_breaks - 1
    new_least_breaks = {}
    if max_breaks == 0:
      continuation_queues[1].append((queue[0], board_hash))
      least_breaks[(queue[0], 1, board_hash)] = (0, 0)
      if build_up_now:
        # upstack by placing up to min(len(queue)-1, 2) pieces
        # ignore everything except board state
        max_upstack_pieces = min(len(queue)-1, 2)

        # add states to queue
        for queue_index in range(max_upstack_pieces):
          for (hold, current_board_hash) in continuation_queues[queue_index]:
            current_state = (hold, queue_index, current_board_hash)
            # Test not using hold, then using hold piece
            for (next_used, next_hold) in ((queue[queue_index], hold), (hold, queue[queue_index])):
              for next_board_hash in board_lib.get_next_boards(current_board_hash, next_used, False, can180):
                next_state = (next_hold, queue_index + 1, next_board_hash)
                immediate_placement_state = (next_hold, next_board_hash)
                if next_state not in least_breaks:
                  least_breaks[next_state] = (0, 0)
                  # guaranteed to not be over index because of max_upstack_pieces
                  if next_state not in states_considered:
                    states_considered.add(next_state)
                    continuation_queues[queue_index + 1].append(immediate_placement_state)

                  # initialize immediate_placements and reversed_immediate_placements
                  if queue_index == 1:
                    if next_state not in reversed_immediate_placements:
                      reversed_immediate_placements[next_state] = {immediate_placement_state:0}
                    if immediate_placement_state not in immediate_placements:
                      immediate_placements[immediate_placement_state] = {}
                  
                  # Update reversed_immediate_placements
                  if queue_index >= 2:
                    if next_state not in reversed_immediate_placements:
                      reversed_immediate_placements[next_state] = {}
                    for start_state in reversed_immediate_placements[current_state]:
                      if (
                        start_state not in reversed_immediate_placements[next_state]
                        or reversed_immediate_placements[current_state][start_state] > reversed_immediate_placements[next_state][start_state]
                      ):
                        reversed_immediate_placements[next_state][start_state] = reversed_immediate_placements[current_state][start_state]
    else:
      # Faster break logic
      for state in least_breaks:
        (hold, queue_index, board_state) = state
        # Test not using hold, then using hold piece
        current_mino_count = board_lib.num_minos(board_state)
        for (next_used, next_hold) in ((queue[queue_index], hold), (hold, queue[queue_index])):
          for next_board_hash in board_lib.get_next_boards(board_state, next_used, False, can180):
            # only allow breaks
            next_state = (next_hold, queue_index + 1, next_board_hash)
            immediate_placement_state = (next_hold, next_board_hash)
            if board_lib.num_minos(next_board_hash) > current_mino_count:
              if next_state not in new_least_breaks:
                new_least_breaks[next_state] = (max_breaks, least_breaks[state][1])
              else:
                new_least_breaks[next_state] = (max_breaks, max(new_least_breaks[next_state][1], least_breaks[state][1]))
              # guaranteed to not be over index because if it was then we found a continuation
              continuation_queues[queue_index + 1].append(immediate_placement_state)

              # initialize immediate_placements and reversed_immediate_placements
              if queue_index == 1:
                if next_state not in reversed_immediate_placements:
                  reversed_immediate_placements[next_state] = {immediate_placement_state:0}
                if immediate_placement_state not in immediate_placements:
                  immediate_placements[immediate_placement_state] = {}
              
              # Update reversed_immediate_placements
              if queue_index >= 2:
                if next_state not in reversed_immediate_placements:
                  reversed_immediate_placements[next_state] = {}
                for start_state in reversed_immediate_placements[state]:
                  if (
                    start_state not in reversed_immediate_placements[next_state]
                    or reversed_immediate_placements[state][start_state] > reversed_immediate_placements[next_state][start_state]
                  ):
                    reversed_immediate_placements[next_state][start_state] = reversed_immediate_placements[state][start_state]

      # add states in new_least_breaks_set to least_breaks
      for state in new_least_breaks:
        # guaranteed to not overwrite anything already in least_breaks
        least_breaks[state] = new_least_breaks[state]

    # BFS to see all ending states
    for queue_index in range(1, len(queue)):
      for (hold, current_board_hash) in continuation_queues[queue_index]:
        current_state = (hold, queue_index, current_board_hash)

        # Test not using hold, then using hold piece
        for (next_used, next_hold) in ((queue[queue_index], hold), (hold, queue[queue_index])):
          next_board_dictionary = board_lib.get_next_boards(current_board_hash, next_used, True, can180)
          for next_board_hash in next_board_dictionary:
            next_state = (next_hold, queue_index + 1, next_board_hash)
            is_spin = next_board_dictionary[next_board_hash][0]

            # If we have already visited least_breaks previously, there is a path with less breaks
            if next_state not in least_breaks:
              next_num_spins = least_breaks[current_state][1]
              if max_breaks == 0 and is_spin:
                next_num_spins += 1
              least_breaks[next_state] = (max_breaks, next_num_spins)
            
              # Add next states to queue
              # Initialize immediate_placements and reversed_immediate_placements
              (next_hold, next_queue_index, next_board_hash) = next_state
              immediate_placement_state = (next_hold, next_board_hash)
              if next_queue_index == 2:
                if next_state not in reversed_immediate_placements:
                  reversed_immediate_placements[next_state] = {immediate_placement_state:int(is_spin)}
                if immediate_placement_state not in immediate_placements:
                  immediate_placements[immediate_placement_state] = {}
              
              # Update reversed_immediate_placements
              if next_queue_index >= 3:
                if next_state not in reversed_immediate_placements:
                  reversed_immediate_placements[next_state] = {}
                if least_breaks[next_state][0] == max_breaks:
                  for start_state in reversed_immediate_placements[current_state]:
                    if (
                      start_state not in reversed_immediate_placements[next_state]
                      or reversed_immediate_placements[current_state][start_state] + int(is_spin) > reversed_immediate_placements[next_state][start_state]
                    ):
                      reversed_immediate_placements[next_state][start_state] = reversed_immediate_placements[current_state][start_state] + int(is_spin)

              # Actually add next states to queue
              if next_state not in states_considered:
                if queue_index + 1 < len(queue):
                  states_considered.add(next_state)
                  continuation_queues[queue_index + 1].append(immediate_placement_state)

    # fill in immediate_placements
    for ending_state in reversed_immediate_placements:
      queue_index = ending_state[1]
      if queue_index == len(queue):
        for immediate_placement in reversed_immediate_placements[ending_state]:
          immediate_placements[immediate_placement][ending_state] = reversed_immediate_placements[ending_state][immediate_placement]

    # Do foresight
    # (hold, queue_index, board_state) -> {set of accommodated next queues -> mino score}
    # it is almost certainly here that needs to be optimized
    # there is a ton of overlap over the 7^foresight queues checked per final state
    accommodated = {}
    if foresight > 0:
      for final_state in least_breaks:
        (hold, queue_index, final_hash) = final_state
        if queue_index != len(queue):
          continue
        current_mino_count = board_lib.num_minos(final_hash)
        accommodated[final_state] = {}
        # foresight queue -> best score
        foresight_scores = {}
        for foresight_queue in board_lib.all_queues(foresight):
          foresight_scores[foresight_queue] = 1000

          # (foresight_queue_index, foresight_board_hash)
          foresight_continuation_queue = deque()
          foresight_continuation_queue.append((0, final_hash))

          # bfs on all ending states that do not break
          # no need to account for hold
          while len(foresight_continuation_queue) > 0:
            current_state = foresight_continuation_queue.popleft()
            (foresight_queue_index, foresight_board_hash) = current_state
            current_mino_count = board_lib.num_minos(foresight_board_hash)

            for next_board_hash in board_lib.get_next_boards(foresight_board_hash, foresight_queue[foresight_queue_index], True, can180):
              next_state = (foresight_queue_index + 1, next_board_hash)
              next_mino_count = board_lib.num_minos(next_board_hash)
              if next_mino_count <= current_mino_count:
                if foresight_queue_index == foresight - 1:
                  # scoring
                  foresight_scores[foresight_queue] = min(foresight_scores[foresight_queue], board_lib.score_num_minos(next_mino_count))
                else:
                  # add to bfs queue
                  foresight_continuation_queue.append(next_state)
        
        # compute accommodated scores
        for foresight_queue in foresight_scores:
          if foresight_scores[foresight_queue] != 1000:
            if (foresight_queue, hold) not in foresight_cache:
              foresight_cache[(foresight_queue, hold)] = list(board_lib.get_input_queues_for_output_sequence(foresight_queue, hold))
            for input_queue in foresight_cache[(foresight_queue, hold)]:
              if input_queue not in accommodated[final_state]:
                accommodated[final_state][input_queue] = foresight_scores[foresight_queue]
              elif foresight_scores[foresight_queue] < accommodated[final_state][input_queue]:
                accommodated[final_state][input_queue] = foresight_scores[foresight_queue]

    # compute scores and return answer. Lower scores are better.
    # Score is 1000 * 10**foresight * expected number of breaks
    # We add 1000 for each unaccommodated next combination
    # We also add number based on future mino count to score

    best_end_state = None
    state = None
    best_score = len(queue) * 1000000 * 10**foresight
    for state in immediate_placements:
      if len(immediate_placements[state]) == 0:
        continue
      score = best_score + 1

      if foresight == 0:
        for end_state in immediate_placements[state]:
          # num breaks portion
          temp_score = least_breaks[end_state][0] * 1000 * 10**foresight
          # mino count portion
          temp_score += board_lib.score_num_minos(board_lib.num_minos(end_state[2])) * len(queue)
          # subtract number based on number of spins
          temp_score -= immediate_placements[state][end_state]
          # update best end score
          score = min(temp_score, score)
      
      # handle foresight
      else:
        max_num_breaks = 0
        
        # best mino score of anything that accommodates a queue
        currently_accommodated = {}
        # spin counts
        currently_accommodated_spins = {}

        for max_num_breaks in range(max_breaks, max_breaks + 2):
          for end_state in immediate_placements[state]:
            if least_breaks[end_state][0] == max_num_breaks:
              for accommodated_queue in accommodated[end_state]:
                if (
                  accommodated_queue not in currently_accommodated
                  or accommodated[end_state][accommodated_queue] <= currently_accommodated[accommodated_queue]
                ):
                  currently_accommodated[accommodated_queue] = accommodated[end_state][accommodated_queue]
                  if (
                    accommodated_queue not in currently_accommodated_spins
                    or immediate_placements[state][end_state] > currently_accommodated_spins[accommodated_queue]
                  ):
                    currently_accommodated_spins[accommodated_queue] = immediate_placements[state][end_state]
          if len(currently_accommodated) > 0:
            break
        
        # num breaks portion
        score = max_num_breaks * 1000 * 10**foresight
        # We add 1000 for each unaccommodated next piece
        score += (7**foresight - len(currently_accommodated)) * 1000
        # mino count portion
        score += sum(currently_accommodated.values()) * len(queue)
        # spins portion
        score -= sum(currently_accommodated_spins.values())
      
      if score < best_score:
        best_score = score
        best_end_state = state

    if best_end_state is not None:
      break
  
  assert best_end_state is not None, "WTF HAPPENED"

  (end_hold, end_hash) = best_end_state

  # output for bot
  finesse_list = []
  used = queue[1]
  if end_hold != queue[0]:
    used = queue[0]
    finesse_list.append("hold")
  # This is such a scuffed pipeline we better fix this
  finesse_transform = {
    board_lib.FINESSE_L : "moveLeft",
    board_lib.FINESSE_R : "moveRight",
    board_lib.FINESSE_CW : "rotateCW",
    board_lib.FINESSE_CCW : "rotateCCW",
    board_lib.FINESSE_180 : "rotate180",
    board_lib.FINESSE_SD : "softDrop"
  }
  for untransformed_finesse in board_lib.get_next_boards(board_hash, used, False, can180)[end_hash][1]:
    finesse_list.append(finesse_transform[untransformed_finesse])
  print(f"{used} {','.join(finesse_list)}")
  
  return best_end_state

# Computes best combo continuation
# if len(queue) - lookahead pieces are placed
# using lookahead previews and foresight prediction
# if finish is true, will attempt to place an additional lookahead - 1 pieces
# (may have suspicious placements at the end)
def get_best_combo_continuation(board_hash: int, queue: str, lookahead: int = 6, foresight: int = 1, can180: bool = True, canHold: bool = True, finish: bool = True) -> list[tuple[str, int]]:
  """Computes best combo continuation, placing `len(queue) - lookahead` pieces.

  `board_hash` is the hash of the input board.

  `queue` is a string containing the hold piece followed by the next pieces.

  `lookahead` is the number of pieces to consider at a time for computation.

  `foresight` is the length of the foresight queue.
  This is used to compute the probability that the next `foresight` pieces will force a non line clear.
  This is then accounted for when selecting a continuation.

  If `can180` is False, then excludes all 180 finesse.

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
    next_state = get_best_next_combo_state(current_hash, hold + window, foresight, can180, canHold)
    (hold, current_hash) = next_state
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

# inf ds simulator
# simulation_length is number of pieces to simulate
def simulate_inf_ds(simulation_length: int = 1000, lookahead: int = 6, foresight: int = 1, well_height: int = 8, canHold: bool = True, tc_cache_filename: str | None = None, starting_state: int = 0) -> list[tuple[str, int]]:
  """Infinite downstack simulator.

  Prints a simulation of the combo decisions taken.

  `simulation_length` is number of pieces to simulate.

  `lookahead` is the number of pieces to consider at a time for computation.

  `foresight` is the length of the foresight queue.
  This is used to compute the probability that the next `foresight` pieces will force a non line clear.
  This is then accounted for when selecting a continuation.

  `well_height` is the amount of garbage to add underneath the stack whenever a piece is placed that does not clear a line.

  If `canHold` is False, then assumes that the hold queue is empty and disallows access to it.

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
  current_minos = 0
  hold = next(pieces)
  window = ""
  for _ in range(lookahead):
    window += next(pieces)
  current_combo = 0

  # precompute garbage wells
  well_multiplier = (16**well_height - 1)//15
  wells = [row_code * well_multiplier for row_code in [7, 11, 13, 14]]

  fc = {}
  
  if tc_cache_filename is not None:
    board_lib.load_caches(tc_cache_filename, True)

  time_sum = 0
  time_num = 0
  for decision_num in range(simulation_length):
    # compute next state
    num_minos = board_lib.num_minos(current_hash)
    upstack = (num_minos in [0, 1, 2, 4, 5])
    next_queue = hold + window if canHold else window
    time_start = time.time()

    #try:
    next_state = get_best_next_combo_state(current_hash, next_queue, foresight, build_up_now=upstack, canHold=canHold, foresight_cache=fc)
    #except:
      #board_lib.save_caches("data/corrupted")
      #break
    time_elapsed = time.time() - time_start
    time_sum += time_elapsed
    time_num += 1
    (hold, current_hash) = next_state
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

  if tc_cache_filename != None:
    board_lib.save_caches(tc_cache_filename)

  return combo_decisions