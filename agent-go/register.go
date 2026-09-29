package main

import "github.com/l0rraine/MWJDR/agent-go/custom/action"

// registerAll 注册全部自定义 action 与 recognition(替代 Python 装饰器机制)
func registerAll() {
	action.RegisterCommonActions()
	action.RegisterRecordIDActions()
	action.RegisterMonsterActions()
	action.RegisterBeastActions()
	action.RegisterLightActions()
	action.RegisterItemBattleActions()
	action.RegisterBearActions()
	action.RegisterGarrisonActions()
	action.RegisterJoinActions()
	action.RegisterMineActions()
	action.RegisterTravelActions()
	action.RegisterDreamActions()
	action.RegisterUniteActions()
	action.RegisterWanderingMerchantActions()
	action.RegisterMysteryMerchantActions()
	action.RegisterUnionShopActions()
	action.RegisterTouhuActions()
}
