# parse kick data from copying contents of https://kick.rqft.workers.dev/srsx

kicks = {}
ifil = open("data/raw_kicks.txt", 'r')
for _p in range(7):
    piece = ifil.readline().strip().split()[-1]
    counter = -1
    rotate_num = 1
    kicks[piece] = {}
    for _ in range(4):
        kicks[piece][_] = {}
        for __ in range(1, 4):
            kicks[piece][_][__] = []
    while True:
        line = ifil.readline().strip()
        if len(line) >= 9:
            counter += 1
            if counter == 4:
                counter -= 4
                if rotate_num == 1:
                    rotate_num = 3
                else:
                    rotate_num = 2
        elif len(line) == 0:
            ifil.readline()
            break
        else:
            line = ifil.readline()
            (x, y) = (int(line[1:3]), int(line[5:7]))
            if rotate_num == 3 and counter % 2 == 1:
                kicks[piece][4 - counter][rotate_num].append((y, x))
            else:
                kicks[piece][counter][rotate_num].append((y, x))
            ifil.readline()
            ifil.readline()
ifil.close()

ofil = open("data/kicks.txt", "w")
for piece in kicks:
    ofil.write(piece + "\n")
    for rotate in range(4):
        for rotate2 in range(1, 4):
            ofil.write(f"{len(kicks[piece][rotate][rotate2])}\n")
            ofil.write("; ".join([f"{y}, {x}" for (y, x) in kicks[piece][rotate][rotate2]]) + "\n")
ofil.close()
return kicks