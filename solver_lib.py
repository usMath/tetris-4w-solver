### IMPORTS ###

from collections import defaultdict, deque
import os

### UTILITY FUNCTIONS ###

# Rotations, used for debugging
ROTATIONS = ["N", "E", "S", "W"]
ROTATION_MOVES = ["0", "CW", "180", "CCW"]

# File names
PIECES_FILENAME = "data/pieces.txt"
KICKS_FILENAME = "data/kicks.txt"
PC_QUEUES_FILENAME = "data/pc-queues.txt"

# Reads piece data from txt file.
# Returns {piece: {orientation: [squares relative to center]}}
# Stored as (y, x)
def get_pieces(filename):
    pieces = {}
    ifil = open(filename, 'r')
    piece_list = ifil.readline().strip()
    for piece in piece_list:
        pieces[piece] = {}
        squares = []
        row1 = ifil.readline().strip()
        row0 = ifil.readline().strip()
        for i in range(4):
            if row0[i] != ".": squares.append((0, i-1))
            if row1[i] != ".": squares.append((1, i-1))
        for rotation in range(4):
            pieces[piece][rotation] = tuple(squares)
            squares = [(-x, y) for (y, x) in squares]
    ifil.close()
    return pieces

PIECES = get_pieces(PIECES_FILENAME)
PIECE_WIDTH = {piece:3 for piece in PIECES}
PIECE_WIDTH["O"] = 2
PIECE_WIDTH["I"] = 4

# Reads kick data from txt file.
# Returns {piece: {orientation: {input: [offset order]}}}
def get_kicks(filename):
    kicks = {}
    ifil = open(filename, 'r')
    for _p in range(7):
        piece = ifil.readline().strip()
        kicks[piece] = {}
        for orientation in range(4):
            kicks[piece][orientation] = {}
            for rotation_input in range(1, 4):
                ifil.readline()
                offsets = ifil.readline().strip().split("; ")
                piece_kicks = [tuple(map(int, _.split(", "))) for _ in offsets]
                kicks[piece][orientation][rotation_input] = piece_kicks
    ifil.close()
    return kicks

KICKS = get_kicks(KICKS_FILENAME)

# Converts a board state to an integer.
# Treats board state like binary string.
# Bits are read top to bottom, and right to left within each row.
def hash_board(board):
    board_hash = 0
    for row in reversed(board):
        for square in reversed(row):
            board_hash *= 2
            board_hash += square
    return board_hash

# Converts an integer to a board state.
def unhash_board(board_hash):
    board = []
    while board_hash > 0:
        row_hash = board_hash % 16
        board_hash //= 16
        board.append([])
        for square_num in range(4):
            board[-1].append(row_hash % 2)
            row_hash //= 2
    return board

# Obtains list of squares in the board.
def get_square_list(board):
    square_list = []
    for y in range(len(board)):
        for x in range(4):
            if board[y][x]:
                square_list.append((y, x))
    return square_list

# Obtains list of ways to insert at most max_lines lines into a board
def lines_to_insert(board_height, max_lines):
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

# Obtains all possible ways to play a queue given one hold.
def get_queue_orders(queue):
    if len(queue) == 1:
        yield queue[0]
        return
    for queue_order in get_queue_orders(queue[1:]):
        yield queue[0] + queue_order
    for queue_order in get_queue_orders(queue[0] + queue[2:]):
        yield queue[1] + queue_order

# Displays a board
def display_board(board_hash):
    board = unhash_board(board_hash)
    print("|    |")
    for row in reversed(board):
        print(f"|{''.join([[' ', '#'][_] for _ in row])}|")
    print("+----+")

# Displays a list of boards
def display_boards(board_hash_list):
    for board_hash in board_hash_list:
        display_board(board_hash)
        print()

### MAIN FUNCTIONS ###

# Computes all possible piece placements given board and piece
# Returns a list of all possible boards.
# Assume 100g.
def get_next_boards(board_hash, piece):
    
    # Obtain board
    board = unhash_board(board_hash)
    square_set = set(get_square_list(board))
    
    # Detect starting position of piece, assuming 100g
    y = len(board) - 1
    while True:
        if y < 0:
            y = 0
            break
        good = True
        for (offset_y, offset_x) in PIECES[piece][0]:
            if (y + offset_y, 1 + offset_x) in square_set:
                good = False
                break
        if not good:
            y += 1
            break
        y -= 1
    
    # State is (y, x, rotation)
    queue = deque()
    queue.append((y, 1, 0))
    visited = set()
    
    # BFS on all possible ending locations for piece, assuming 100g
    while len(queue) > 0:
        current = queue.popleft()
        if current not in visited:
            visited.add(current)
            (y, x, rotation) = current
            
            # test movement
            for x_move in (-1, 1):
                new_y_offset = 1
                good = True
                while good:
                    new_y_offset -= 1
                    for (offset_y, offset_x) in PIECES[piece][rotation]:
                        (new_y, new_x) = (y + offset_y + new_y_offset, x + offset_x + x_move)
                        if (new_y, new_x) in square_set or not (0 <= new_y and 0 <= new_x < 4):
                            good = False
                            new_y_offset += 1
                            break
                if new_y_offset <= 0:
                    queue.append((y + new_y_offset, x + x_move, rotation))
            
            # test rotation
            for rotation_move in (1, 2, 3):
                new_rotation = (rotation + rotation_move) % 4
                for (kick_offset_y, kick_offset_x) in KICKS[piece][rotation][rotation_move]:
                    new_y_position = kick_offset_y + y
                    new_x_position = kick_offset_x + x
                    good = True
                    for (offset_y, offset_x) in PIECES[piece][new_rotation]:
                        (new_y, new_x) = (new_y_position + offset_y, new_x_position + offset_x)
                        if (new_y, new_x) in square_set or not (0 <= new_y and 0 <= new_x < 4):
                            good = False
                            break
                    if good:
                        # gravity
                        while good:
                            new_y_position -= 1
                            for (offset_y, offset_x) in PIECES[piece][new_rotation]:
                                (new_y, new_x) = (new_y_position + offset_y, new_x_position + offset_x)
                                if (new_y, new_x) in square_set or not (0 <= new_y and 0 <= new_x < 4):
                                    good = False
                                    new_y_position += 1
                                    break
                        queue.append((new_y_position, new_x_position, new_rotation))
                        break
    
    # Obtain board states
    boards = set()
    for (y, x, rotation) in visited:
        new_hash = board_hash
        for (offset_y, offset_x) in PIECES[piece][rotation]:
            new_hash += 2**(4 * (y + offset_y) + x + offset_x)
        new_board = unhash_board(new_hash)
        
        # Remove completed lines
        cleared_board = [_ for _ in new_board if 0 in _]
        
        boards.add(hash_board(cleared_board))
    
    return sorted(boards)

# Computes all possible board states at the end of the given queue
def get_next_boards_given_queue(board_hash, queue):
    boards = set([board_hash])
    for piece in queue:
        new_boards = set()
        for board in boards:
            new_boards = new_boards.union(set(get_next_boards(board, piece)))
        boards = new_boards
    return sorted(boards)

# Computes all possible previous piece placements given board and previous piece
# Returns a list of all possible previous boards.
# Assume 100g.
def get_previous_boards(board_hash, piece, forwards_saved_transitions = {}):
    
    # Obtain board
    board = unhash_board(board_hash)
    
    # Obtain potential board states such that adding the given piece would result in current board state
    candidate_previous_boards = set()
    for line_list in lines_to_insert(len(board), PIECE_WIDTH[piece]):
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
        square_set = set(get_square_list(candidate_previous_board))
        for y in range(len(candidate_previous_board)):
            for x in range(4):
                for rotation in range(4):
                    good = True
                    piece_hash = 0
                    for (offset_y, offset_x) in PIECES[piece][rotation]:
                        (new_y, new_x) = (y + offset_y, x + offset_x)
                        if (new_y, new_x) not in square_set:
                            good = False
                            break
                        piece_hash += 2**(4 * new_y + new_x)
                    
                    # Compute hash and check for lack of filled in lines
                    if good:
                        processed_previous_board_hash = candidate_previous_board_hash - piece_hash
                        processed_previous_board = unhash_board(processed_previous_board_hash)
                        if False not in [0 in row for row in processed_previous_board]:
                            candidate_previous_boards.add(processed_previous_board_hash)
    
    candidate_previous_boards = sorted(candidate_previous_boards)
    # Ensure it is possible to reach current board state from each candidate previous board state
    boards = []
    for candidate_previous_board in candidate_previous_boards:
        if (candidate_previous_board, piece) not in forwards_saved_transitions:
            forwards_saved_transitions[(candidate_previous_board, piece)] = get_next_boards(candidate_previous_board, piece)
        if board_hash in forwards_saved_transitions[(candidate_previous_board, piece)]:
            boards.append(candidate_previous_board)
    
    return boards

# Computes all possible board states that at the end of the given queue results in the given board
def get_previous_boards_given_queue(board_hash, queue):
    boards = set([board_hash])
    forwards_saved_transitions = {}
    for piece in reversed(queue):
        prev_boards = set()
        for board in boards:
            prev_boards = prev_boards.union(set(get_previous_boards(board, piece, forwards_saved_transitions)))
        boards = prev_boards
    return sorted(boards)

# Generate all PC queues for any possible queue up to length N.
# Limits max height to H.
# Reads from output file if one exists.
# Otherwise, saves to output file because this is gonna take FOREVER.
def generate_all_pc_queues(filename, n = 8, h = 8, override = False):
    if not override and os.path.isfile(filename):
        ifil = open(filename, 'r')
        N = int(ifil.readline().strip())
        pcs = [ifil.readline().strip() for _ in range(N)]
        ifil.close()
        return pcs
    
    h = min(n, h)
    pcs = set()
    
    max_board = 2**(4*h) - 1  # max hash
    
    # Optimization: use BFS forwards and backwards
    n_backwards = n//4 + 1
    n_forwards = n - n_backwards
    
    # Backwards direction
    backwards_queue = deque()
    backwards_queue.append((0, ""))  # (board_hash, history)
    backwards_reachable_states = defaultdict(set)  # board_hash -> queue_set
    backwards_saved_transitions = {}  # (board_hash, piece) -> next_board_list
    forwards_saved_transitions = {}  # (board_hash, piece) -> next_board_list
    
    visited = set()
    while len(backwards_queue) > 0:
        current = backwards_queue.popleft()
        if current not in visited:
            visited.add(current)
            (board_hash, history) = current
            
            # Check each possible next piece
            for piece in PIECES:
                new_history = piece + history
                if (board_hash, piece) not in backwards_saved_transitions:
                    backwards_saved_transitions[(board_hash, piece)] = get_previous_boards(board_hash, piece, forwards_saved_transitions)
                for previous_board in backwards_saved_transitions[(board_hash, piece)]:
                    # Track reachable board states
                    if previous_board != 0 and previous_board < max_board:
                        backwards_reachable_states[previous_board].add(new_history)
                        if len(new_history) < n_backwards:
                            backwards_queue.append((previous_board, new_history))
    
    # Forwards direction
    forwards_queue = deque()
    forwards_queue.append((0, ""))  # (board_hash, history)
    forwards_reachable_states = defaultdict(set)  # board_hash -> queue_set
    
    visited = set()
    while len(forwards_queue) > 0:
        current = forwards_queue.popleft()
        if current not in visited:
            visited.add(current)
            (board_hash, history) = current
            
            # Check each possible next piece
            for piece in PIECES:
                new_history = history + piece
                if (board_hash, piece) not in forwards_saved_transitions:
                    forwards_saved_transitions[(board_hash, piece)] = get_next_boards(board_hash, piece)
                for next_board in forwards_saved_transitions[(board_hash, piece)]:
                    # Track reachable board states
                    if next_board < max_board and next_board != 0:
                        if next_board in backwards_reachable_states:
                            forwards_reachable_states[next_board].add(new_history)
                        if len(new_history) < n_forwards:
                            forwards_queue.append((next_board, new_history))
    
    # Merge forwards and backwards
    for board_hash in forwards_reachable_states:
        if board_hash in backwards_reachable_states:
            for first_half in forwards_reachable_states[board_hash]:
                for second_half in backwards_reachable_states[board_hash]:
                    pcs.add(first_half + second_half)
    
    pcs.add("I")  # Edge case
    
    # Save to output file
    ofil = open(filename, 'w')
    pcs = sorted(pcs, key = lambda pc: (len(pc), pc))
    ofil.write(str(len(pcs)) + "\n")
    ofil.write("\n".join(pcs))
    ofil.close()
    return pcs

# Determines the set of saves for a given pc queue ("X" if no save), given set of pcs.
def get_pc_saves(piece_queue, pcs):
    saves = {}
    for queue_order in get_queue_orders(piece_queue):
        if queue_order[:-1] in pcs:
            saves[queue_order[-1]] = queue_order[:-1]
        if queue_order in pcs:
            saves["X"] = queue_order
    return saves

# Computes the maximum number of pcs that can be obtained in a queue.
def max_pcs_in_queue(piece_queue):
    pcs = set(generate_all_pc_queues(PC_QUEUES_FILENAME))  # set of all pcs
    max_n = len(max(pcs, key = lambda _:len(_)))  # longest pc
    piece_queue = piece_queue + "X"  # terminator character
    dp = {(1, piece_queue[0]): (0, None, None)}  # (index, hold piece) -> (num pcs, previous state, previous solve)
    for index in range(1, len(piece_queue)):
        for hold in PIECES:
            current_state = (index, hold)
            if current_state in dp:
                for pieces_used in range(1, min(len(piece_queue) + 1 - index, max_n + 1)):
                    pc_queue = hold + piece_queue[index:index + pieces_used]
                    saves = get_pc_saves(pc_queue, pcs)
                    for save in saves:
                        next_state = (index + pieces_used, save)
                        if next_state not in dp or dp[current_state][0] + 1 > dp[next_state][0]:
                            dp[next_state] = (dp[current_state][0] + 1, current_state, saves[save])
    (max_pcs, current_state, prev_solve) = max(dp.values())
    if max_pcs == 0:
        return (0, [])
    reversed_history = [prev_solve,]
    while dp[current_state][2] != None:
        reversed_history.append(dp[current_state][2])
        current_state = dp[current_state][1]
    history = list(reversed(reversed_history))
    return (max_pcs, history)