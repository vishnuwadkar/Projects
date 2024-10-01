'''
 1 - snake
-1 - water
 0 - gun
'''
print("S - snake\tW - water\tG - gun")
import random   #random module to generate random choice for computer

compStr = random.choice(["S","W","G"])  #generating random choice using choice method from random module
youStr = input("Enter your choice: ")
numDict = {"S":1,"W":-1,"G":0}
nameDict = {"S":"Snake","W":"Water","G":"Gun"}
you = numDict[youStr]
comp = numDict[compStr]
def play():
    #When computer chooses  water
    if comp == -1:
        if  you == 1:
            print("You win!")
        elif you == 0:
            print("Computer wins!")
        else:
            print("draw!")

    #When computer chooses  gun
    if comp == 0:
        if  you == 1:
            print("Computer wins!")
        elif you == 0:
            print("draw!")
        else:
            print("You win!")

    #When computer chooses  snake

    if comp == 1:
        if  you == 1:
            print("draw!")
        elif you == 0:
            print("You win!")
        else:
            print("Computer wins!")

#begin
print(f"Your choice : {nameDict[youStr]}")
print(f"Computer choice : {nameDict[compStr]}")
play()
