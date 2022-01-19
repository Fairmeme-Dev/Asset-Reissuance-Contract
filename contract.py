from pyteal import *

def approval_program():

    @Subroutine(TealType.none)
    def OptIn(asset_id):
        return Seq(
            InnerTxnBuilder.Begin(),
            InnerTxnBuilder.SetFields(
                {
                    TxnField.xfer_asset:asset_id,
                    TxnField.type_enum:TxnType.AssetTransfer,
                    TxnField.asset_amount:Int(0),
                    TxnField.asset_receiver:Global.current_application_address()
                }
            ),
            InnerTxnBuilder.Submit(),
        )

    asset_pair_a = Int(12345678) # old ASA to receive
    asset_pair_b = Int(87654321) # new ASA to send

    on_init = Seq([
        Approve()
    ])
    
    on_create = Seq([
        Approve()
    ])

    # subroutine to specify ASA, address and amount to send
    
    @Subroutine(TealType.none)
    def sendAssets(address, asa_id, amount):
        return Seq(
            InnerTxnBuilder.Begin(),
            InnerTxnBuilder.SetFields(
                {
                    TxnField.type_enum:TxnType.AssetTransfer,
                    TxnField.xfer_asset:asa_id,
                    TxnField.sender:Global.current_application_address(),
                    TxnField.asset_receiver:address,
                    TxnField.asset_amount:amount
                }
            ),
            InnerTxnBuilder.Submit(),
        )

    asset_decimals = Int(6) # new ASA decimals (must be certain and accurate to avoid misspend)

    multiplier = Int(10) ** asset_decimals # multiply old ASA send amount by this amount to get amount to send for new ASA

    on_swap = Seq(
        If (
            And(
                Global.group_size() == Int(2), # group size must be two (ApplicationCall and AssetTransfer)
                Gtxn[0].type_enum() == TxnType.ApplicationCall,
                Gtxn[1].asset_amount() >= Int(1) # ASA sent must be greater than or equal to 1
            )
        ).Then(
            Seq(
                If (
                    And(
                        Gtxn[1].type_enum() == TxnType.AssetTransfer, # make sure it is an asset transfer txn
                        Gtxn[1].xfer_asset() == asset_pair_a, # make sure it is the right ASA ID
                        Gtxn[1].asset_receiver() == Global.current_application_address() # make sure ASA is sent to the contract escrow account
                    )
                ).Then(
                    Seq(
                        sendAssets(Txn.sender(), asset_pair_b, Gtxn[1].asset_amount() * multiplier),
                        Approve()
                    )
                ).Else(
                    Reject()
                )
            )
        ),
        Reject()
    )

    # Fund the contract escrow account with the new tokens
    # Opt asset in to both tokens to let it receive the asset_pair_a and send asset_pair_b

    on_fund = Seq(
        If (
            And(
                Txn.sender() == Global.creator_address(), # must be initiated by creator to avoid misuse attack
                Global.group_size() == Int(2), # group size must be 2
                Gtxn[0].type_enum() == TxnType.ApplicationCall,
                Gtxn[1].type_enum() == TxnType.AssetTransfer,
                Gtxn[1].xfer_asset() == asset_pair_a, # must be known asset pair
                Gtxn[1].asset_amount() >= Int(1), # ASA sent must be >= 1
                Gtxn[1].asset_receiver() == Global.current_application_address() # must be targeted to contract escrow account
            )
        ).Then(
            Seq(
                OptIn(asset_pair_a), # optin ASA pair A
                OptIn(asset_pair_b), #optin ASA pair B
                Approve()
            )
        ),
        Reject()
    )
    
    on_call_method = Txn.application_args[0]
    

    # App main routing

    # For all app calls, make sure the asset_pair_a and asset_pair_b ASAs are specified as foreign Assets
    
    on_call = Cond(
        [on_call_method == Bytes("swap"), on_swap],
        [on_call_method == Bytes("fund"), on_fund],
        [on_call_method == Bytes("init"), on_init]
    )
    
    program = Cond(
        [Txn.application_id() == Int(0), on_create],
        [
            Or(
                Txn.on_completion() == OnComplete.OptIn,
                Txn.on_completion() == OnComplete().NoOp
            ),
            on_call
            # NO update, delete or closeout
        ],
        [
            Or(
                Txn.on_completion() == OnComplete.CloseOut,
                Txn.on_completion() == OnComplete.UpdateApplication,
                Txn.on_completion() == OnComplete.DeleteApplication
            ),
            Reject()
        ]
    )
    return program

def clear_program():
    return Return(Int(1))

#compile teals
if __name__ == "__main__":
    with open("approval.teal", "w") as f:
        compiled = compileTeal(approval_program(), mode=Mode.Application, version=5)
        f.write(compiled)

    with open("clear.teal", "w") as f:
        compiled = compileTeal(clear_program(), mode=Mode.Application, version=5)
        f.write(compiled)