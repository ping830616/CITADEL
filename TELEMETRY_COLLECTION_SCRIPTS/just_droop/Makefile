CFLAGS =  -Wall -O0
all: operation 

operation: operation.o
	gcc $(CFLAGS) -o operation operation.o -lpthread

operation.o: operation.c
	gcc $(CFLAGS) -c -o operation.o operation.c -mrdrnd


clean:
	rm -f operation.o operation
