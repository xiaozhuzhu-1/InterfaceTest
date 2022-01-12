import os
from django.conf import settings

from django.forms import model_to_dict
# from django.http import HttpResponse
from django.shortcuts import render
from django.views.generic import View
from schema import Schema, And, Optional

from interface_app.models.case import TestCase
from interface_app.models.task import Task, TaskTestCase, RunTask
from interface_app.utils.response import response_success, response_failed, ErrorCode
import datetime
import json
from interface_app.views.case_views import test_case_model_to_dict

from apscheduler.schedulers.background import BackgroundScheduler
from django_apscheduler.jobstores import DjangoJobStore, register_job, register_events
try:
    # 实例化调度器
    scheduler = BackgroundScheduler()
    # 调度器使用DjangoJobStore()
    scheduler.add_jobstore(DjangoJobStore(), "default")
    # 设置定时任务，选择方式为interval，时间间隔为10s
    # 另一种方式为每天固定时间执行任务，对应代码为：

    # def my_job():
    #     # 这里写你要执行的任务
    #     print("myjob")
    register_events(scheduler)
    scheduler.start()

    # scheduler.add_job(my_job, 'interval', seconds=10, id="test")
    # scheduler.remove_job("test")
except Exception as e:
    print(e)
    # 有错误就停止定时器
    scheduler.shutdown()


class TaskView(View):
    update_schema = Schema({Optional('name'): And(str, lambda s: 0 < len(s) < 256),
                            Optional('description'): str,
                            Optional('project_id'): int})
    # Optional代表字段是可选   and代表需要满足所有条件
    # put方法修改数据必须进行参数的校验，需要更新的时候做个表单校验。就得用schema

    def get(self, request, task_id, *args, **kwargs):
        """
        请求是单个数据
        :param request:
        :param task_id:
        :param args:
        :param kwargs:
        :return:
        """
        task = Task.objects.filter(id=task_id).first()
        if not task:
            return response_failed(code=ErrorCode.task, message='数据不存在')
        task_dict = model_to_dict(task)
        return response_success(data=task_dict)

    def put(self, request, task_id, *args, **kwargs):
        """
        这个是修改数据
        :param request:
        :param task_id:
        :param args:
        :param kwargs:
        :return:
        """
        task = Task.objects.filter(id=task_id).first()
        # django的filter方法是从数据库的取得匹配的结果，返回一个对象列表，如果记录不存在的话，它会返回[]。注.objects.all()、.objects.get()区别

        if not task:
            return response_failed(code=ErrorCode.task, message='数据不存在')

        body = request.body
        data = json.loads(body, encoding='utf-8')
        if not self.update_schema.is_valid(data):
            return response_failed()

        data = self.update_schema.validate(data)    # validate(data)其中data应是json实例，所以上面data转下json
        if not data:  # 如果没有传数据，就不需要处理
            pass
        else:
            Task.objects.filter(id=task_id).update(**data)
            task = Task.objects.filter(id=task_id).first()

        task_dict = model_to_dict(task)
        return response_success(data=task_dict)

    def delete(self, request, task_id, *args, **kwargs):
        """
        这个是删除数据
        :param request:
        :param task_id:
        :param args:
        :param kwargs:
        :return:
        """
        Task.objects.filter(id=task_id).delete()
        return response_success(data=True)

class TasksView(View):
    create_schema = Schema({'name': And(str, lambda s: 0 < len(s) < 256),
                            'description': str,
                            'project_id': int})

    def get(self, request, *args, **kwargs):
        """
        请求列表数据
        :param request:
        :param args:
        :param kwargs:
        :return:
        """
        project_id = request.GET.get('project_id')
        task = Task.objects.filter(project_id=project_id)
        if not project_id:
            return response_success(data=[])
        ret = []
        for item in task:
            tmp = model_to_dict(item)
            ret.append(tmp)
        return response_success(data=ret)

    def post(self, request, *args, **kwargs):
        """
        创建数据
        :param request:
        :param args:
        :param kwargs:
        :return:
        """
        body = request.body
        data = json.loads(body, encoding='utf-8')
        if not self.create_schema.is_valid(data):
            return response_failed()
        data = self.create_schema.validate(data)
        task = Task.objects.create(**data)
        task_dict = model_to_dict(task)
        return response_success(data=task_dict)

class TaskTestCasesView(View):
    def get(self, request, task_id, *args, **kwargs):
        """
        请求任务的用例列表数据
        :param request:
        :param args:
        :param task_id:
        :param kwargs:
        :return:
        """
        task_cases = TaskTestCase.objects.filter(task_id=task_id)
        ret = []
        for item in task_cases:
            case = TestCase.objects.get(id=item.test_case_id)
            tmp = test_case_model_to_dict(case)
            tmp['task_test_case_id'] = item.id
            ret.append(tmp)
        return response_success(data=ret)

    def post(self, request, task_id, *args, **kwargs):
        """
        创建数据
        :param request:
        :param args:
        :param task_id:
        :param kwargs:
        :return:
        """
        create_schema = Schema({'test_case_ids': list})

        body = request.body
        data = json.loads(body, encoding='utf-8')
        if not create_schema.is_valid(data):
            return response_failed()
        data = create_schema.validate(data)

        test_case_ids = data['test_case_ids']
        for item in test_case_ids:
            # 以下相当于查询语句：select test_case_id from tasktestcase where task_id
            task_case_ids = TaskTestCase.objects.filter(task_id=task_id).values_list("test_case_id", flat=True)

            # 需要判断下用例是否被导入过
            if item in task_case_ids:
                pass
            else:
                TaskTestCase.objects.create(task_id=task_id, test_case_id=item)
        return response_success()

    def delete(self, request, task_id, *args, **kwargs):
        """
        删除数据
        :param request:
        :param task_id:
        :param args:
        :param kwargs:
        :return:
        """
        # 注：通过get请求获取，则前端写请求request时要把参数放在url中
        task_test_case_id = request.GET.get('task_test_case_id')
        if not task_test_case_id:
            return response_failed()

        TaskTestCase.objects.filter(id=task_test_case_id).delete()
        return response_success()

class TaskRunTestCaseView(View):
    def post(self, request, task_id, *args, **kwargs):
        """
        任务执行
        :param request:
        :param task_id:
        :param args:
        :param kwargs:
        :return:
        """
        run_task_common(task_id)
        return response_success()

def run_task_common(task_id):
    task_report_path = os.path.join(settings.BASE_DIR, "task_test", "reports", str(task_id), )
    if not os.path.exists(task_report_path):    # 若无当前目录会创建个
        os.makedirs(task_report_path)

    RunTask.objects.create(task_id=task_id)  # 由于django和pytest无法互通信，则使用数据库做中转。存入后，pytest执行时再去数据库中取最近一条的数据task_id

    now = datetime.datetime.now()
    report_name = now.strftime("%Y-%m-%d--%H:%M:%S")+".html"

    run_task_path = os.path.join(settings.BASE_DIR, "task_test", "run_task.py")
    report_path = os.path.join(settings.BASE_DIR, "task_test", "reports", str(task_id), report_name)
    command = "pytest " "-vs " + run_task_path + " --html=" + report_path
    # command = "pytest " "-vs " + run_task_path + " --alluredir ./temp"
    print(command)
    os.system(command)
    # allure_commend = "allure generate ./temp -o " + report_path + " --clean"
    # os.system(allure_commend)


class TaskReportListView(View):
    def get(self, request, task_id, *args, **kwargs):
        """
        获取report列表
        :param request:
        :param task_id:
        :param args:
        :param kwargs:
        :return:
        """
        # os.path.join()将多个路径组合后返回
        task_reports_path = os.path.join(settings.BASE_DIR, "task_test", "reports", str(task_id),)
        list_name = []
        if not os.path.exists(task_reports_path):
            return response_success(list_name)

        for file in os.listdir(task_reports_path):  # os.listdir(path)返回指定路径下的文件和文件夹列表
                # os.path.splitext(path)将对应路径的文件名和后缀名分割，[1]取后缀名
            list_name.append({"name": file})    # append() 方法用于在列表末尾添加新的对象
        print("报告列表名称"+str(list_name))
        list_name = sorted(list_name, key=lambda x: x['name'], reverse=True)    # sorted（）返回重新排序的列表.reverse = True 降序
        return response_success(list_name)


class TaskReportDetailView(View):
    def get(self, request, task_id, report_name, *args, **kwargs):
        """
        获取report列表
        :param request:
        :param task_id:
        :param args:
        :param kwargs:
        :return:
        """
        return render(request, str(task_id) + "/" + report_name)

class TaskIntervalRunTestCaseView(View):
    update_schema = Schema({'days': And(int, lambda s: 0 <= s),
                            'hours': And(int, lambda s: 0 <= s),
                            'minutes': And(int, lambda s: 0 <= s),
                            'start_time': str})
    def post(self, request, task_id, *args, **kwargs):
        """
        任务循环执行
        :param request:
        :param task_id:
        :param args:
        :param kwargs:
        :return:
        """
        task = Task.objects.filter(id=task_id).first()
        if not task:
            return response_failed(code=ErrorCode.task, message='数据不存在')

        body = request.body
        data = json.loads(body, encoding='utf-8')  # 把字符串转成python对象，日常工作中最常见的就是把字符串通过json.loads转为字典
        if not self.update_schema.is_valid(data):
            return response_failed()

        data = self.update_schema.validate(data)
        if not data:    # 如果没有传数据，就不需要处理
            pass
        else:
            data['interval_switch'] = True
            Task.objects.filter(id=task_id).update(**data)

        job = scheduler.get_job("task"+str(task_id))
        if job:
            scheduler.remove_job("task"+str(task_id))
        scheduler.add_job(run_task_common, 'interval', args=[task_id], days=data["days"], hours=data["hours"],
                          minutes=data["minutes"], start_date=data["start_time"], id="task" + str(task_id))
        return response_success()

    def delete(self, request, task_id, *args, **kwargs):
        """
        停止任务循环执行
        :param request:
        :param task_id:
        :param args:
        :param kwargs:
        :return:
        """
        task = Task.objects.filter(id=task_id).first()
        if not task:
            return response_failed(code=ErrorCode.task, message='数据不存在')
        data = {
            "interval_switch": False,
            "days": 0,
            "hours": 0,
            "minutes": 0,
            "start_time": None
        }
        Task.objects.filter(id=task_id).update(**data)

        job = scheduler.get_job("task" + str(task_id))
        if job:
            scheduler.remove_job("task" + str(task_id))
        return response_success()

