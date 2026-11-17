# Ground-truth index (failed mutants)

One document per mutant whose JPF classification is not `Pass`. Root cause = the injected mutation.

## Outcome per operator

| Operator | Mutants | JPF failed | JPF passed | Failure classes |
| --- | --- | --- | --- | --- |
| `lock_order_inversion_blocks` | 9 | 4 | 5 | Deadlock: 4 |
| `lock_order_inversion_methods` | 25 | 13 | 12 | Deadlock: 13 |
| `missing_notify` | 1 | 1 | 0 | Deadlock: 1 |
| `missing_release` | 2 | 1 | 1 | Deadlock: 1 |
| `monitor_misuse` | 2 | 2 | 0 | Uncaught Exception: 2 |
| `rm_join` | 47 | 28 | 19 | Termination Error: 5, Uncaught Exception: 23 |
| `rm_sync_block` | 15 | 9 | 6 | Race Condition: 9 |
| `rm_sync_one` | 33 | 16 | 17 | Race Condition: 16 |
| `rm_volatile` | 4 | 0 | 4 | - |
| `semaphore_starve` | 1 | 1 | 0 | Deadlock: 1 |
| `unguarded_wait` | 1 | 1 | 0 | Deadlock: 1 |
| `unsafe_collection` | 8 | 0 | 8 | - |
| `wrong_lock` | 47 | 23 | 24 | Race Condition: 23 |

## Documents

| Mutant | Operator | JPF classification | Document |
| --- | --- | --- | --- |
| `1-rm_sync_block-0` | `rm_sync_block` | Race Condition | [1-rm_sync_block-0.md](1-rm_sync_block-0.md) |
| `1-rm_sync_block-1` | `rm_sync_block` | Race Condition | [1-rm_sync_block-1.md](1-rm_sync_block-1.md) |
| `1-wrong_lock-0` | `wrong_lock` | Race Condition | [1-wrong_lock-0.md](1-wrong_lock-0.md) |
| `1-wrong_lock-1` | `wrong_lock` | Race Condition | [1-wrong_lock-1.md](1-wrong_lock-1.md) |
| `1-rm_join-1` | `rm_join` | Termination Error | [1-rm_join-1.md](1-rm_join-1.md) |
| `1-lock_order_inversion_blocks-0` | `lock_order_inversion_blocks` | Deadlock | [1-lock_order_inversion_blocks-0.md](1-lock_order_inversion_blocks-0.md) |
| `2-rm_sync_block-0` | `rm_sync_block` | Race Condition | [2-rm_sync_block-0.md](2-rm_sync_block-0.md) |
| `2-rm_sync_block-1` | `rm_sync_block` | Race Condition | [2-rm_sync_block-1.md](2-rm_sync_block-1.md) |
| `2-wrong_lock-0` | `wrong_lock` | Race Condition | [2-wrong_lock-0.md](2-wrong_lock-0.md) |
| `2-wrong_lock-1` | `wrong_lock` | Race Condition | [2-wrong_lock-1.md](2-wrong_lock-1.md) |
| `2-rm_join-0` | `rm_join` | Termination Error | [2-rm_join-0.md](2-rm_join-0.md) |
| `2-lock_order_inversion_blocks-0` | `lock_order_inversion_blocks` | Deadlock | [2-lock_order_inversion_blocks-0.md](2-lock_order_inversion_blocks-0.md) |
| `3-rm_sync_block-0` | `rm_sync_block` | Race Condition | [3-rm_sync_block-0.md](3-rm_sync_block-0.md) |
| `3-rm_sync_block-1` | `rm_sync_block` | Race Condition | [3-rm_sync_block-1.md](3-rm_sync_block-1.md) |
| `3-wrong_lock-0` | `wrong_lock` | Race Condition | [3-wrong_lock-0.md](3-wrong_lock-0.md) |
| `3-wrong_lock-1` | `wrong_lock` | Race Condition | [3-wrong_lock-1.md](3-wrong_lock-1.md) |
| `3-rm_join-0` | `rm_join` | Termination Error | [3-rm_join-0.md](3-rm_join-0.md) |
| `3-lock_order_inversion_blocks-0` | `lock_order_inversion_blocks` | Deadlock | [3-lock_order_inversion_blocks-0.md](3-lock_order_inversion_blocks-0.md) |
| `49-rm_join-0` | `rm_join` | Termination Error | [49-rm_join-0.md](49-rm_join-0.md) |
| `49-rm_join-1` | `rm_join` | Termination Error | [49-rm_join-1.md](49-rm_join-1.md) |
| `49-lock_order_inversion_methods-0` | `lock_order_inversion_methods` | Deadlock | [49-lock_order_inversion_methods-0.md](49-lock_order_inversion_methods-0.md) |
| `68-rm_sync_one-0` | `rm_sync_one` | Race Condition | [68-rm_sync_one-0.md](68-rm_sync_one-0.md) |
| `68-rm_sync_one-1` | `rm_sync_one` | Race Condition | [68-rm_sync_one-1.md](68-rm_sync_one-1.md) |
| `68-wrong_lock-0` | `wrong_lock` | Race Condition | [68-wrong_lock-0.md](68-wrong_lock-0.md) |
| `68-wrong_lock-1` | `wrong_lock` | Race Condition | [68-wrong_lock-1.md](68-wrong_lock-1.md) |
| `68-lock_order_inversion_methods-0` | `lock_order_inversion_methods` | Deadlock | [68-lock_order_inversion_methods-0.md](68-lock_order_inversion_methods-0.md) |
| `73-rm_sync_one-0` | `rm_sync_one` | Race Condition | [73-rm_sync_one-0.md](73-rm_sync_one-0.md) |
| `73-rm_sync_one-1` | `rm_sync_one` | Race Condition | [73-rm_sync_one-1.md](73-rm_sync_one-1.md) |
| `73-wrong_lock-0` | `wrong_lock` | Race Condition | [73-wrong_lock-0.md](73-wrong_lock-0.md) |
| `73-wrong_lock-1` | `wrong_lock` | Race Condition | [73-wrong_lock-1.md](73-wrong_lock-1.md) |
| `73-lock_order_inversion_methods-0` | `lock_order_inversion_methods` | Deadlock | [73-lock_order_inversion_methods-0.md](73-lock_order_inversion_methods-0.md) |
| `74-rm_join-0` | `rm_join` | Uncaught Exception | [74-rm_join-0.md](74-rm_join-0.md) |
| `74-rm_join-1` | `rm_join` | Uncaught Exception | [74-rm_join-1.md](74-rm_join-1.md) |
| `74-monitor_misuse-0` | `monitor_misuse` | Uncaught Exception | [74-monitor_misuse-0.md](74-monitor_misuse-0.md) |
| `74-monitor_misuse-1` | `monitor_misuse` | Uncaught Exception | [74-monitor_misuse-1.md](74-monitor_misuse-1.md) |
| `74-missing_notify-0` | `missing_notify` | Deadlock | [74-missing_notify-0.md](74-missing_notify-0.md) |
| `74-unguarded_wait-0` | `unguarded_wait` | Deadlock | [74-unguarded_wait-0.md](74-unguarded_wait-0.md) |
| `80-rm_sync_one-0` | `rm_sync_one` | Race Condition | [80-rm_sync_one-0.md](80-rm_sync_one-0.md) |
| `80-rm_join-0` | `rm_join` | Uncaught Exception | [80-rm_join-0.md](80-rm_join-0.md) |
| `80-rm_join-1` | `rm_join` | Uncaught Exception | [80-rm_join-1.md](80-rm_join-1.md) |
| `86-rm_sync_one-0` | `rm_sync_one` | Race Condition | [86-rm_sync_one-0.md](86-rm_sync_one-0.md) |
| `86-rm_sync_one-1` | `rm_sync_one` | Race Condition | [86-rm_sync_one-1.md](86-rm_sync_one-1.md) |
| `86-wrong_lock-0` | `wrong_lock` | Race Condition | [86-wrong_lock-0.md](86-wrong_lock-0.md) |
| `86-wrong_lock-1` | `wrong_lock` | Race Condition | [86-wrong_lock-1.md](86-wrong_lock-1.md) |
| `86-lock_order_inversion_methods-0` | `lock_order_inversion_methods` | Deadlock | [86-lock_order_inversion_methods-0.md](86-lock_order_inversion_methods-0.md) |
| `87-rm_join-0` | `rm_join` | Uncaught Exception | [87-rm_join-0.md](87-rm_join-0.md) |
| `87-rm_join-1` | `rm_join` | Uncaught Exception | [87-rm_join-1.md](87-rm_join-1.md) |
| `87-lock_order_inversion_methods-2` | `lock_order_inversion_methods` | Deadlock | [87-lock_order_inversion_methods-2.md](87-lock_order_inversion_methods-2.md) |
| `90-rm_sync_one-0` | `rm_sync_one` | Race Condition | [90-rm_sync_one-0.md](90-rm_sync_one-0.md) |
| `90-rm_sync_one-1` | `rm_sync_one` | Race Condition | [90-rm_sync_one-1.md](90-rm_sync_one-1.md) |
| `90-wrong_lock-0` | `wrong_lock` | Race Condition | [90-wrong_lock-0.md](90-wrong_lock-0.md) |
| `90-wrong_lock-1` | `wrong_lock` | Race Condition | [90-wrong_lock-1.md](90-wrong_lock-1.md) |
| `90-lock_order_inversion_methods-0` | `lock_order_inversion_methods` | Deadlock | [90-lock_order_inversion_methods-0.md](90-lock_order_inversion_methods-0.md) |
| `91-rm_sync_one-0` | `rm_sync_one` | Race Condition | [91-rm_sync_one-0.md](91-rm_sync_one-0.md) |
| `91-rm_sync_one-1` | `rm_sync_one` | Race Condition | [91-rm_sync_one-1.md](91-rm_sync_one-1.md) |
| `91-wrong_lock-0` | `wrong_lock` | Race Condition | [91-wrong_lock-0.md](91-wrong_lock-0.md) |
| `91-wrong_lock-1` | `wrong_lock` | Race Condition | [91-wrong_lock-1.md](91-wrong_lock-1.md) |
| `91-lock_order_inversion_methods-0` | `lock_order_inversion_methods` | Deadlock | [91-lock_order_inversion_methods-0.md](91-lock_order_inversion_methods-0.md) |
| `96-rm_sync_block-0` | `rm_sync_block` | Race Condition | [96-rm_sync_block-0.md](96-rm_sync_block-0.md) |
| `96-rm_sync_block-1` | `rm_sync_block` | Race Condition | [96-rm_sync_block-1.md](96-rm_sync_block-1.md) |
| `96-rm_sync_block-2` | `rm_sync_block` | Race Condition | [96-rm_sync_block-2.md](96-rm_sync_block-2.md) |
| `96-wrong_lock-0` | `wrong_lock` | Race Condition | [96-wrong_lock-0.md](96-wrong_lock-0.md) |
| `96-wrong_lock-1` | `wrong_lock` | Race Condition | [96-wrong_lock-1.md](96-wrong_lock-1.md) |
| `96-wrong_lock-2` | `wrong_lock` | Race Condition | [96-wrong_lock-2.md](96-wrong_lock-2.md) |
| `96-rm_join-0` | `rm_join` | Uncaught Exception | [96-rm_join-0.md](96-rm_join-0.md) |
| `96-rm_join-1` | `rm_join` | Uncaught Exception | [96-rm_join-1.md](96-rm_join-1.md) |
| `96-rm_join-2` | `rm_join` | Uncaught Exception | [96-rm_join-2.md](96-rm_join-2.md) |
| `97-rm_join-0` | `rm_join` | Uncaught Exception | [97-rm_join-0.md](97-rm_join-0.md) |
| `97-semaphore_starve-0` | `semaphore_starve` | Deadlock | [97-semaphore_starve-0.md](97-semaphore_starve-0.md) |
| `97-missing_release-1` | `missing_release` | Deadlock | [97-missing_release-1.md](97-missing_release-1.md) |
| `99-lock_order_inversion_methods-0` | `lock_order_inversion_methods` | Deadlock | [99-lock_order_inversion_methods-0.md](99-lock_order_inversion_methods-0.md) |
| `99-lock_order_inversion_methods-1` | `lock_order_inversion_methods` | Deadlock | [99-lock_order_inversion_methods-1.md](99-lock_order_inversion_methods-1.md) |
| `99-lock_order_inversion_methods-2` | `lock_order_inversion_methods` | Deadlock | [99-lock_order_inversion_methods-2.md](99-lock_order_inversion_methods-2.md) |
| `100-rm_join-0` | `rm_join` | Uncaught Exception | [100-rm_join-0.md](100-rm_join-0.md) |
| `101-rm_join-0` | `rm_join` | Uncaught Exception | [101-rm_join-0.md](101-rm_join-0.md) |
| `101-rm_join-1` | `rm_join` | Uncaught Exception | [101-rm_join-1.md](101-rm_join-1.md) |
| `105-rm_sync_one-0` | `rm_sync_one` | Race Condition | [105-rm_sync_one-0.md](105-rm_sync_one-0.md) |
| `105-rm_sync_one-1` | `rm_sync_one` | Race Condition | [105-rm_sync_one-1.md](105-rm_sync_one-1.md) |
| `105-wrong_lock-0` | `wrong_lock` | Race Condition | [105-wrong_lock-0.md](105-wrong_lock-0.md) |
| `105-wrong_lock-1` | `wrong_lock` | Race Condition | [105-wrong_lock-1.md](105-wrong_lock-1.md) |
| `105-rm_join-0` | `rm_join` | Uncaught Exception | [105-rm_join-0.md](105-rm_join-0.md) |
| `105-rm_join-1` | `rm_join` | Uncaught Exception | [105-rm_join-1.md](105-rm_join-1.md) |
| `105-lock_order_inversion_methods-0` | `lock_order_inversion_methods` | Deadlock | [105-lock_order_inversion_methods-0.md](105-lock_order_inversion_methods-0.md) |
| `112-rm_join-0` | `rm_join` | Uncaught Exception | [112-rm_join-0.md](112-rm_join-0.md) |
| `112-rm_join-1` | `rm_join` | Uncaught Exception | [112-rm_join-1.md](112-rm_join-1.md) |
| `112-lock_order_inversion_methods-0` | `lock_order_inversion_methods` | Deadlock | [112-lock_order_inversion_methods-0.md](112-lock_order_inversion_methods-0.md) |
| `113-rm_join-0` | `rm_join` | Uncaught Exception | [113-rm_join-0.md](113-rm_join-0.md) |
| `113-rm_join-1` | `rm_join` | Uncaught Exception | [113-rm_join-1.md](113-rm_join-1.md) |
| `113-lock_order_inversion_blocks-0` | `lock_order_inversion_blocks` | Deadlock | [113-lock_order_inversion_blocks-0.md](113-lock_order_inversion_blocks-0.md) |
| `114-rm_sync_one-1` | `rm_sync_one` | Race Condition | [114-rm_sync_one-1.md](114-rm_sync_one-1.md) |
| `114-rm_join-0` | `rm_join` | Uncaught Exception | [114-rm_join-0.md](114-rm_join-0.md) |
| `114-rm_join-1` | `rm_join` | Uncaught Exception | [114-rm_join-1.md](114-rm_join-1.md) |
| `115-rm_sync_one-0` | `rm_sync_one` | Race Condition | [115-rm_sync_one-0.md](115-rm_sync_one-0.md) |
| `115-rm_sync_one-1` | `rm_sync_one` | Race Condition | [115-rm_sync_one-1.md](115-rm_sync_one-1.md) |
| `115-wrong_lock-0` | `wrong_lock` | Race Condition | [115-wrong_lock-0.md](115-wrong_lock-0.md) |
| `115-wrong_lock-1` | `wrong_lock` | Race Condition | [115-wrong_lock-1.md](115-wrong_lock-1.md) |
| `115-rm_join-0` | `rm_join` | Uncaught Exception | [115-rm_join-0.md](115-rm_join-0.md) |
| `115-rm_join-1` | `rm_join` | Uncaught Exception | [115-rm_join-1.md](115-rm_join-1.md) |
| `115-lock_order_inversion_methods-0` | `lock_order_inversion_methods` | Deadlock | [115-lock_order_inversion_methods-0.md](115-lock_order_inversion_methods-0.md) |
