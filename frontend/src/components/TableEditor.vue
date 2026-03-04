<template>
  <div class="table-editor">
    <div class="table-toolbar">
      <el-button type="primary" size="small" @click="addRow">
        <el-icon><plus /></el-icon> 添加行
      </el-button>
      <el-button type="danger" size="small" :disabled="!selectedRows.length" @click="deleteRows">
        <el-icon><delete /></el-icon> 删除选中
      </el-button>
    </div>
    
    <ag-grid-vue
      class="ag-theme-alpine"
      :style="{ height: gridHeight }"
      :columnDefs="columnDefs"
      :rowData="rowData"
      :defaultColDef="defaultColDef"
      :rowSelection="'multiple'"
      @grid-ready="onGridReady"
      @selection-changed="onSelectionChanged"
      @cell-value-changed="onCellValueChanged"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { AgGridVue } from 'ag-grid-vue3'
import { Plus, Delete } from '@element-plus/icons-vue'
import type { GridApi, ColDef, GridReadyEvent, CellValueChangedEvent } from 'ag-grid-community'
import 'ag-grid-community/styles/ag-grid.css'
import 'ag-grid-community/styles/ag-theme-alpine.css'

interface Props {
  data: any[]
  columns: string[]
  editable?: boolean
  height?: string
}

const props = withDefaults(defineProps<Props>(), {
  editable: true,
  height: '500px'
})

const emit = defineEmits<{
  dataChange: [data: any[]]
}>()

const gridApi = ref<GridApi>()
const rowData = ref<any[]>([...props.data])
const selectedRows = ref<any[]>([])
const gridHeight = ref(props.height)

// 列定义
const columnDefs = ref<ColDef[]>(
  props.columns.map((col, index) => ({
    field: col,
    headerName: col,
    editable: props.editable && index > 0, // 第一列（表头）不可编辑
    lockPosition: index === 0, // 锁定第一列
    sortable: true,
    filter: true,
    resizable: true,
    cellEditor: 'agTextCellEditor',
    valueParser: (params: any) => {
      // IP 格式验证
      if (col.toLowerCase().includes('ip')) {
        const ipRegex = /^(\d{1,3}\.){3}\d{1,3}$/
        if (!ipRegex.test(params.newValue)) {
          return params.oldValue
        }
      }
      // 端口范围验证
      if (col.toLowerCase().includes('port')) {
        const port = parseInt(params.newValue)
        if (isNaN(port) || port < 0 || port > 65535) {
          return params.oldValue
        }
      }
      return params.newValue
    }
  }))
)

// 默认列配置
const defaultColDef = ref<ColDef>({
  flex: 1,
  minWidth: 100,
  cellStyle: { textAlign: 'left' }
})

// 监听数据变化
watch(() => props.data, (newData) => {
  rowData.value = [...newData]
  if (gridApi.value) {
    gridApi.value.setRowData(rowData.value)
  }
}, { deep: true })

const onGridReady = (params: GridReadyEvent) => {
  gridApi.value = params.api
}

const onSelectionChanged = () => {
  if (gridApi.value) {
    selectedRows.value = gridApi.value.getSelectedRows()
  }
}

const onCellValueChanged = (event: CellValueChangedEvent) => {
  emit('dataChange', rowData.value)
}

const addRow = () => {
  const newRow: any = {}
  props.columns.forEach(col => {
    newRow[col] = ''
  })
  rowData.value.push(newRow)
  gridApi.value?.setRowData(rowData.value)
  emit('dataChange', rowData.value)
}

const deleteRows = () => {
  if (!gridApi.value) return
  
  const selectedData = gridApi.value.getSelectedRows()
  rowData.value = rowData.value.filter(row => !selectedData.includes(row))
  gridApi.value.setRowData(rowData.value)
  emit('dataChange', rowData.value)
}
</script>

<style scoped>
.table-editor {
  width: 100%;
}

.table-toolbar {
  margin-bottom: 10px;
  display: flex;
  gap: 10px;
}

.ag-theme-alpine {
  width: 100%;
}
</style>
