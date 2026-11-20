// PLHM_DevTools (test only, never shipped): swap the user's helmet + ear-pro kit from the demo box.
class PLHM_DemoKitAction : ScriptedUserAction
{
	[Attribute("", UIWidgets.ResourceNamePicker, desc: "Helmet prefab", params: "et")]
	protected ResourceName m_rHelmet;

	[Attribute("", UIWidgets.ResourceNamePicker, desc: "Ear-pro prefab for that helmet family", params: "et")]
	protected ResourceName m_rEarPro;

	override bool CanBePerformedScript(IEntity user)
	{
		return !PLHM_EarProService.FindEarPro(user) || !PLHM_EarProService.FindEarPro(user).IsBusy();
	}

	override void PerformAction(IEntity pOwnerEntity, IEntity pUserEntity)
	{
		if (!Replication.IsServer())
			return;
		SCR_InventoryStorageManagerComponent inv = SCR_InventoryStorageManagerComponent.Cast(pUserEntity.FindComponent(SCR_InventoryStorageManagerComponent));
		SCR_CharacterInventoryStorageComponent cs = SCR_CharacterInventoryStorageComponent.Cast(pUserEntity.FindComponent(SCR_CharacterInventoryStorageComponent));
		if (!inv || !cs)
			return;
		// remove the current head cover
		for (int i = 0; i < cs.GetSlotsCount(); i++)
		{
			InventoryStorageSlot slot = cs.GetSlot(i);
			if (!slot || !slot.GetAttachedEntity())
				continue;
			BaseLoadoutClothComponent cl = BaseLoadoutClothComponent.Cast(slot.GetAttachedEntity().FindComponent(BaseLoadoutClothComponent));
			if (cl && cl.GetAreaType() && cl.GetAreaType().ClassName() == "LoadoutHeadCoverArea")
				inv.TryDeleteItem(slot.GetAttachedEntity());
		}
		IEntity helmet = Spawn(m_rHelmet, pUserEntity);
		if (helmet && inv.EquipAny(cs, helmet))
			GetGame().GetCallqueue().CallLater(InsertEarPro, 800, false, pUserEntity, helmet, m_rEarPro);
	}

	protected static IEntity Spawn(ResourceName r, IEntity near)
	{
		Resource res = Resource.Load(r);
		if (!res || !res.IsValid())
			return null;
		EntitySpawnParams sp();
		sp.TransformMode = ETransformMode.WORLD;
		near.GetTransform(sp.Transform);
		sp.Transform[3] = sp.Transform[3] + "0 2.5 0";
		return GetGame().SpawnEntityPrefab(res, GetGame().GetWorld(), sp);
	}

	protected static void InsertEarPro(IEntity user, IEntity helmet, ResourceName earpro)
	{
		if (!user || !helmet)
			return;
		BaseInventoryStorageComponent st = BaseInventoryStorageComponent.Cast(helmet.FindComponent(ClothNodeStorageComponent));
		SCR_InventoryStorageManagerComponent inv = SCR_InventoryStorageManagerComponent.Cast(user.FindComponent(SCR_InventoryStorageManagerComponent));
		IEntity e = Spawn(earpro, user);
		if (e && st && inv)
			Print(string.Format("[PLHM] kit ear-pro %1 -> %2", earpro, inv.TryInsertItemInStorage(e, st, -1)), LogLevel.NORMAL);
	}
}
